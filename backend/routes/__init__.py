from flask import Blueprint

auth_bp = Blueprint('auth', __name__)
customers_bp = Blueprint('customers', __name__)
business_bp = Blueprint('business', __name__)
contracts_bp = Blueprint('contracts', __name__)
finance_bp = Blueprint('finance', __name__)
dashboard_bp = Blueprint('dashboard', __name__)
system_bp = Blueprint('system', __name__)
misc_bp = Blueprint('misc', __name__)
visits_bp = Blueprint('visits', __name__)
reports_bp = Blueprint('reports', __name__)
erp_bp = Blueprint('erp', __name__)
custom_fields_bp = Blueprint('custom_fields', __name__)
work_summary_bp = Blueprint('work_summary', __name__)
business_tags_bp = Blueprint('business_tags', __name__)
data_sources_bp = Blueprint('data_sources', __name__)
ai_agent_bp = Blueprint('ai_agent', __name__)
knowledge_bp = Blueprint('knowledge', __name__)
knowledge_ext_bp = Blueprint('knowledge_ext', __name__)
knowledge_graph_bp = Blueprint('knowledge_graph', __name__)
leads_bp = Blueprint('leads', __name__)
agent_agent_bp = Blueprint('agent_agent', __name__)
enterprises_bp = Blueprint('enterprises', __name__)
products_bp = Blueprint('products', __name__)
quotes_bp = Blueprint('quotes', __name__)
marketing_bp = Blueprint('marketing', __name__)
tickets_bp = Blueprint('tickets', __name__)
security_bp = Blueprint('security', __name__)

# Phase1: 关键词管理 + 原始情报
keywords_bp = Blueprint('keywords', __name__)
intelligence_bp = Blueprint('intelligence', __name__)

# Phase6: AI驾驶舱
cockpit_bp = Blueprint('cockpit', __name__)


def register_blueprints(app):
    from .auth import register_routes as register_auth
    from .customers import register_routes as register_customers
    from .business import register_routes as register_business
    from .contracts import register_routes as register_contracts
    from .finance import register_routes as register_finance
    from .dashboard import register_routes as register_dashboard
    from .system import register_routes as register_system
    from .misc import register_routes as register_misc
    from .visits import register_routes as register_visits
    from .reports import register_routes as register_reports
    from .erp import register_routes as register_erp
    from .custom_fields import register_routes as register_custom_fields
    from .work_summary import register_routes as register_work_summary
    from .business_tags import register_routes as register_business_tags
    from .data_sources import register_routes as register_data_sources
    from .ai_agent import register_routes as register_ai_agent
    from .knowledge import register_routes as register_knowledge
    from .knowledge_ext import register_routes as register_knowledge_ext
    from .knowledge_graph import register_routes as register_knowledge_graph
    from .leads import register_routes as register_leads
    from .agent_agent import register_routes as register_agent_agent
    from .enterprises import register_routes as register_enterprises
    from .products import register_routes as register_products
    from .quotes import register_routes as register_quotes
    from .marketing import register_routes as register_marketing
    from .tickets import register_routes as register_tickets
    from .security_api import register_routes as register_security_api
    from .keywords import register_routes as register_keywords
    from .intelligence import register_routes as register_intelligence
    from .cockpit import register_routes as register_cockpit
    from .tasks import register_routes as register_tasks
    from .capabilities import register_routes as register_capabilities

    # Phase9: LLM Gateway（/api/ai/*）
    from llm_gateway import register_routes as register_ai_gateway

    register_auth(app)
    register_customers(app)
    register_business(app)
    register_contracts(app)
    register_finance(app)
    register_dashboard(app)
    register_system(app)
    register_misc(app)
    register_visits(app)
    register_reports(app)
    register_erp(app)
    register_custom_fields(app)
    register_work_summary(app)
    register_business_tags(app)
    register_data_sources(app)
    register_ai_agent(app)
    register_knowledge(app)
    register_knowledge_ext(app)
    register_knowledge_graph(app)
    register_leads(app)
    register_agent_agent(app)
    register_enterprises(app)
    register_products(app)
    register_quotes(app)
    register_marketing(app)
    register_tickets(app)
    register_security_api(app)
    register_keywords(app)
    register_intelligence(app)
    register_cockpit(app)
    register_tasks(app)
    register_capabilities(app)
    register_ai_gateway(app)

    from .smart_import import smart_import_bp
    app.register_blueprint(smart_import_bp)

    from .appraisal import appraisal_bp
    app.register_blueprint(appraisal_bp, url_prefix='/api/appraisal')
