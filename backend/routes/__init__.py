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
ai_agent_bp = Blueprint('ai_agent', __name__)
knowledge_bp = Blueprint('knowledge', __name__)
leads_bp = Blueprint('leads', __name__)

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
    from .ai_agent import register_routes as register_ai_agent
    from .knowledge import register_routes as register_knowledge
    from .leads import register_routes as register_leads

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
    register_ai_agent(app)
    register_knowledge(app)
    register_leads(app)
