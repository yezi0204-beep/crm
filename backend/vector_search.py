"""向量检索引擎 - 支持语义搜索和知识匹配"""
import json
import math
import hashlib
import sqlite3
import os
import re
from datetime import datetime
from config import LLM_API_KEY, LLM_API_BASE, LLM_MODEL, USE_LLM


def _get_db():
    from extensions import DB_PATH
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _simple_hash_vector(text, dim=384):
    """基于文本哈希的伪向量生成（无LLM时的降级方案）。

    将文本的字符分布哈希到指定维度的向量空间，用于相似度计算。
    """
    if not text:
        return [0.0] * dim

    vector = [0.0] * dim
    text_bytes = text.encode('utf-8', errors='ignore')

    for i in range(min(len(text_bytes), 2000)):
        b = text_bytes[i]
        idx = (b * 31 + i * 7) % dim
        vector[idx] += 1.0

    norm = math.sqrt(sum(x * x for x in vector))
    if norm > 0:
        vector = [x / norm for x in vector]

    return vector


def _keyword_vector(text, keywords):
    """基于关键词匹配的向量生成（规则方法）。"""
    if not text or not keywords:
        return [0.0] * len(keywords)

    text_lower = text.lower()
    vector = []
    for kw in keywords:
        count = text_lower.count(kw.lower())
        vector.append(float(count))

    norm = math.sqrt(sum(x * x for x in vector))
    if norm > 0:
        vector = [x / norm for x in vector]

    return vector


def cosine_similarity(vec_a, vec_b):
    """计算两个向量的余弦相似度。"""
    if not vec_a or not vec_b:
        return 0.0

    min_len = min(len(vec_a), len(vec_b))
    if min_len == 0:
        return 0.0

    vec_a = vec_a[:min_len]
    vec_b = vec_b[:min_len]

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def generate_embedding(text):
    """生成文本的语义向量。

    LLM可用时调用embedding API，否则降级为哈希向量。
    """
    if not text or not text.strip():
        return None

    text = text.strip()

    if USE_LLM and LLM_API_KEY:
        try:
            import requests
            headers = {
                'Authorization': f'Bearer {LLM_API_KEY}',
                'Content-Type': 'application/json'
            }
            payload = {
                'model': 'text-embedding-3-small',
                'input': text[:8000]
            }
            response = requests.post(
                f'{LLM_API_BASE}/embeddings',
                headers=headers,
                json=payload,
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                return data['data'][0]['embedding']
        except Exception as e:
            print(f"[VectorSearch] LLM embedding failed: {e}")

    return _simple_hash_vector(text)


def chunk_text(text, max_chunk_size=500, overlap=50):
    """将文本分块。"""
    if not text:
        return []

    chunks = []
    sentences = re.split(r'[。！？\n]', text)
    current_chunk = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(current_chunk) + len(sentence) <= max_chunk_size:
            current_chunk += sentence + "。"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence + "。"

            if len(sentence) > max_chunk_size:
                while len(current_chunk) > max_chunk_size:
                    chunks.append(current_chunk[:max_chunk_size])
                    current_chunk = current_chunk[max_chunk_size - overlap:]

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


def index_document(doc_id, text):
    """为文档建立向量索引。"""
    conn = _get_db()
    cursor = conn.cursor()

    chunks = chunk_text(text)
    vectors = []

    for idx, chunk in enumerate(chunks):
        embedding = generate_embedding(chunk)
        if embedding:
            vectors.append({
                'doc_id': doc_id,
                'chunk_index': idx,
                'chunk_text': chunk,
                'vector': json.dumps(embedding),
                'vector_dim': len(embedding)
            })

    cursor.execute("DELETE FROM knowledge_vectors WHERE doc_id = ?", (doc_id,))

    for v in vectors:
        cursor.execute("""
            INSERT INTO knowledge_vectors (doc_id, chunk_index, chunk_text, vector, vector_dim, embedding_model)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (v['doc_id'], v['chunk_index'], v['chunk_text'], v['vector'], v['vector_dim'],
              'text-embedding-3-small' if USE_LLM else 'hash'))

    cursor.execute("""
        UPDATE knowledge_documents
        SET processed = 1, processed_at = ?
        WHERE id = ?
    """, (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), doc_id))

    conn.commit()
    conn.close()

    return len(vectors)


def semantic_search(query, doc_type=None, cust_id=None, business_id=None, top_k=5):
    """语义搜索知识库文档。

    支持：
    - 纯向量相似度搜索
    - 关键词混合搜索（向量+关键词加权）
    - 过滤器（doc_type/cust_id/business_id）
    """
    query_embedding = generate_embedding(query)
    if not query_embedding:
        return []

    conn = _get_db()
    cursor = conn.cursor()

    conditions = []
    params = []

    if doc_type:
        conditions.append("d.doc_type = ?")
        params.append(doc_type)
    if cust_id:
        conditions.append("d.cust_id = ?")
        params.append(cust_id)
    if business_id:
        conditions.append("d.business_id = ?")
        params.append(business_id)

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    cursor.execute(f"""
        SELECT v.*, d.doc_type, d.title, d.cust_id, d.business_id, d.summary
        FROM knowledge_vectors v
        JOIN knowledge_documents d ON v.doc_id = d.id
        {where_clause}
    """, params)

    results = []
    for row in cursor.fetchall():
        vector = json.loads(row['vector']) if row['vector'] else []
        similarity = cosine_similarity(query_embedding, vector)

        title_score = 0.0
        if row['chunk_text']:
            title_lower = row['chunk_text'].lower()
            query_lower = query.lower()
            query_words = [w for w in query_lower if len(w) > 1]
            word_matches = sum(1 for w in query_words if w in title_lower)
            if query_words:
                title_score = word_matches / len(query_words)

        final_score = similarity * 0.7 + title_score * 0.3

        results.append({
            'doc_id': row['doc_id'],
            'doc_type': row['doc_type'],
            'title': row['title'],
            'chunk_index': row['chunk_index'],
            'chunk_text': row['chunk_text'],
            'similarity': round(final_score, 4),
            'cust_id': row['cust_id'],
            'business_id': row['business_id'],
            'summary': row['summary']
        })

    results.sort(key=lambda x: x['similarity'], reverse=True)
    results = results[:top_k]

    conn.close()
    return results


def find_similar_documents(doc_id, top_k=5, doc_type=None):
    """查找与指定文档相似的其他文档。"""
    conn = _get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT vector FROM knowledge_vectors WHERE doc_id = ? ORDER BY chunk_index LIMIT 1", (doc_id,))
    row = cursor.fetchone()
    if not row or not row['vector']:
        conn.close()
        return []

    query_vector = json.loads(row['vector'])

    conditions = ["v.doc_id != ?"]
    params = [doc_id]
    if doc_type:
        conditions.append("d.doc_type = ?")
        params.append(doc_type)

    where_clause = "WHERE " + " AND ".join(conditions)

    cursor.execute(f"""
        SELECT v.*, d.doc_type, d.title, d.cust_id, d.summary
        FROM knowledge_vectors v
        JOIN knowledge_documents d ON v.doc_id = d.id
        {where_clause}
    """, params)

    results = []
    seen_docs = set()
    for row in cursor.fetchall():
        if row['doc_id'] in seen_docs:
            continue

        vector = json.loads(row['vector']) if row['vector'] else []
        similarity = cosine_similarity(query_vector, vector)

        if similarity > 0.3:
            results.append({
                'doc_id': row['doc_id'],
                'doc_type': row['doc_type'],
                'title': row['title'],
                'similarity': round(similarity, 4),
                'summary': row['summary']
            })
            seen_docs.add(row['doc_id'])

    results.sort(key=lambda x: x['similarity'], reverse=True)
    results = results[:top_k]

    conn.close()
    return results


def hybrid_search(query, filters=None, top_k=5):
    """混合搜索：向量语义 + 关键词匹配 + 元数据过滤。"""
    vector_results = semantic_search(
        query,
        doc_type=filters.get('doc_type') if filters else None,
        cust_id=filters.get('cust_id') if filters else None,
        business_id=filters.get('business_id') if filters else None,
        top_k=top_k * 2
    )

    keyword_results = []
    conn = _get_db()
    cursor = conn.cursor()

    keyword_conditions = []
    keyword_params = []

    if filters and filters.get('doc_type'):
        keyword_conditions.append("doc_type = ?")
        keyword_params.append(filters['doc_type'])
    if filters and filters.get('cust_id'):
        keyword_conditions.append("cust_id = ?")
        keyword_params.append(filters['cust_id'])
    if filters and filters.get('business_id'):
        keyword_conditions.append("business_id = ?")
        keyword_params.append(filters['business_id'])

    where_parts = ["(title LIKE ? OR content LIKE ? OR tags LIKE ?)"]
    search_kw = f'%{query}%'
    keyword_params.extend([search_kw, search_kw, search_kw])

    if keyword_conditions:
        where_parts.extend(keyword_conditions)

    cursor.execute(f"""
        SELECT * FROM knowledge_documents
        WHERE {' AND '.join(where_parts)}
        ORDER BY created_at DESC
        LIMIT {top_k}
    """, keyword_params)

    for row in cursor.fetchall():
        doc = dict(row)
        title_lower = (doc.get('title', '') + doc.get('content', '')).lower()
        query_lower = query.lower()
        keyword_score = 0.0
        if query_lower in title_lower:
            keyword_score = 0.8
        else:
            query_words = [w for w in query_lower if len(w) > 1]
            word_matches = sum(1 for w in query_words if w in title_lower)
            if query_words:
                keyword_score = word_matches / len(query_words) * 0.5

        keyword_results.append({
            'doc_id': doc['id'],
            'doc_type': doc['doc_type'],
            'title': doc['title'],
            'similarity': round(keyword_score, 4),
            'source': 'keyword',
            'summary': doc.get('summary', ''),
            'cust_id': doc.get('cust_id'),
            'business_id': doc.get('business_id')
        })

    conn.close()

    merged = {}
    for r in vector_results:
        r['source'] = 'vector'
        merged[r['doc_id']] = r

    for r in keyword_results:
        if r['doc_id'] in merged:
            merged[r['doc_id']]['similarity'] = max(
                merged[r['doc_id']]['similarity'],
                r['similarity']
            )
        else:
            merged[r['doc_id']] = r

    final_results = sorted(merged.values(), key=lambda x: x['similarity'], reverse=True)
    return final_results[:top_k]


def rebuild_all_vectors():
    """重建所有文档的向量索引。"""
    conn = _get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, content FROM knowledge_documents WHERE processed = 0 OR processed IS NULL")
    docs = cursor.fetchall()

    processed = 0
    failed = 0
    for doc in docs:
        text = f"{doc['title']}\n{doc['content'] or ''}"
        try:
            index_document(doc['id'], text)
            processed += 1
        except Exception as e:
            failed += 1
            print(f"[VectorSearch] Failed to index doc {doc['id']}: {e}")

    conn.close()
    return {'processed': processed, 'failed': failed, 'total': len(docs)}


def get_knowledge_stats():
    """获取知识库统计信息。"""
    conn = _get_db()
    cursor = conn.cursor()

    stats = {}

    cursor.execute("SELECT doc_type, COUNT(*) as cnt FROM knowledge_documents GROUP BY doc_type")
    stats['by_type'] = {row['doc_type']: row['cnt'] for row in cursor.fetchall()}

    cursor.execute("SELECT COUNT(*) as total FROM knowledge_documents")
    stats['total_documents'] = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as total FROM knowledge_vectors")
    stats['total_vectors'] = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as total FROM knowledge_documents WHERE processed = 0")
    stats['unprocessed'] = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as total FROM personnel_qualifications WHERE status='有效'")
    stats['personnel_qualifications'] = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as total FROM company_qualifications WHERE status='有效'")
    stats['company_qualifications'] = cursor.fetchone()['total']

    conn.close()
    return stats