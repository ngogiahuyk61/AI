from odoo import http
from odoo.http import request

class CustomHomepage(http.Controller):
    
    @http.route('/odoo', type='http', auth='user', website=True)
    def custom_homepage(self, **kwargs):
        """Custom homepage route"""
        try:
            # Get available modules/apps for the current user
            user = request.env.user
            available_modules = self._get_user_modules(user)
            
            return request.render('custom_homepage.homepage_template', {
                'modules': available_modules,
                'user': user,
            })
        except Exception as e:
            # Fallback if there's an error
            return request.redirect('/web')
    
    @http.route('/', type='http', auth='none')
    def root_redirect(self, **kw):
        """Redirect root to custom homepage if logged in"""
        if request.session.uid:
            return request.redirect('/odoo')
        else:
            return request.redirect('/web/login')
    
    def _get_user_modules(self, user):
        """Get available modules for the user based on their groups"""
        modules = []
        
        # Define module configurations
        module_configs = [
            {
                'name': 'Sales',
                'icon': 'fa-shopping-cart',
                'action': '/web#action=sale.action_orders',
                'groups': ['sales_team.group_sale_salesman', 'sales_team.group_sale_manager'],
                'color': 'bg-primary'
            },
            {
                'name': 'Purchase',
                'icon': 'fa-shopping-bag',
                'action': '/web#action=purchase.purchase_order_action_generic',
                'groups': ['purchase.group_purchase_user', 'purchase.group_purchase_manager'],
                'color': 'bg-success'
            },
            {
                'name': 'Inventory',
                'icon': 'fa-cubes',
                'action': '/web#action=stock.dashboard_action',
                'groups': ['stock.group_stock_user', 'stock.group_stock_manager'],
                'color': 'bg-warning'
            },
            {
                'name': 'Accounting',
                'icon': 'fa-calculator',
                'action': '/web#action=account.action_move_journal_line',
                'groups': ['account.group_account_user', 'account.group_account_manager'],
                'color': 'bg-info'
            },
            {
                'name': 'HR',
                'icon': 'fa-users',
                'action': '/web#action=hr.open_view_employee_list_my',
                'groups': ['hr.group_hr_user', 'hr.group_hr_manager'],
                'color': 'bg-secondary'
            },
            {
                'name': 'CRM',
                'icon': 'fa-handshake-o',
                'action': '/web#action=crm.crm_lead_action_pipeline',
                'groups': ['sales_team.group_sale_salesman'],
                'color': 'bg-dark'
            },
            {
                'name': 'Manufacturing',
                'icon': 'fa-cogs',
                'action': '/web#action=mrp.mrp_production_action',
                'groups': ['mrp.group_mrp_user'],
                'color': 'bg-danger'
            },
            {
                'name': 'Project',
                'icon': 'fa-tasks',
                'action': '/web#action=project.action_view_project',
                'groups': ['project.group_project_user'],
                'color': 'bg-purple'
            },
            {
                'name': 'Settings',
                'icon': 'fa-cog',
                'action': '/web#action=base.action_res_config_settings',
                'groups': ['base.group_system'],
                'color': 'bg-muted'
            }
        ]
        
        # Check user access for each module
        for module in module_configs:
            has_access = False
            for group_xml_id in module.get('groups', []):
                try:
                    group = request.env.ref(group_xml_id, raise_if_not_found=False)
                    if group and user.id in group.users.ids:
                        has_access = True
                        break
                except:
                    continue
            
            if has_access or user.has_group('base.group_system'):
                modules.append(module)
        
        return modules