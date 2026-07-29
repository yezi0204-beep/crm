from flask import Blueprint

auth_bp = Blueprint('auth', __name__)
customers_bp = Blueprint('customers', __name__)
business_bp = Blueprint('business', __name__)
contracts_bp = Blueprint('contracts', __name__)
finance_bp = Blueprint('finance', __name__)
dashboard_bp = Blueprint('dashboard', __name__)
system_bp = Blueprint('system', __name__)
misc_bp = Blueprint('misc', __name__)

def register_blueprints(app):
    from .auth import register_routes as register_auth
    from .customers import register_routes as register_customers
    from .business import register_routes as register_business
    from .contracts import register_routes as register_contracts
    from .finance import register_routes as register_finance
    from .dashboard import register_routes as register_dashboard
    from .system import register_routes as register_system
    from .misc import register_routes as register_misc

    register_auth(app)
    register_customers(app)
    register_business(app)
    register_contracts(app)
    register_finance(app)
    register_dashboard(app)
    register_system(app)
    register_misc(app)
