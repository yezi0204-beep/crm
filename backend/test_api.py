from app import app

with app.test_client() as client:
    login_response = client.post('/api/auth/login', json={'username': 'yewei', 'password': '123456'})
    token = login_response.get_json()['data']['token']
    
    auth_header = 'Bearer ' + token
    qa_response = client.post(
        '/api/qa',
        json={'question': '我负责的客户有多少个？', 'stream': False},
        headers={'Authorization': auth_header}
    )
    
    data = qa_response.get_json()
    print('Code:', data['code'])
    print('Message:', data['message'])
    print('Answer:', data['data']['answer'][:200], '...')
