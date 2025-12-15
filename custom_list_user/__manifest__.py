{
    'name': 'Custom Company List User',
    'version': '1.0',
    'depends': ['base','web'],
    'data': [
        'views/res_user_views.xml',
    ],
    'assets': {
        'web.assets_common': [
            'custom_list_user/static/src/scss/list_user.scss',
        ],
        'web.assets_backend': [
            'custom_list_user/static/src/scss/list_user.scss',
        ],
        'web.assets_frontend': [
            'custom_list_user/static/src/scss/list_user.scss',
        ],
    },
    'installable': True,
    'application': False,
}