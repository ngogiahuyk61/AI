{
    'name': 'Custom Homepage',
    'version': '1.0.0',
    'category': 'Tools',
    'summary': 'Custom homepage with module buttons',
    'description': 'Custom homepage with module navigation buttons',
    'author': 'Your Name',
    'depends': ['base', 'web'],
    'data': [
        'views/homepage_template.xml',
    ],
    'assets': {
        'web.assets_common': [
            'custom_homepage/static/src/scss/homepage.scss',
            'custom_homepage/static/src/js/homepage.js',
        ],
        'web.assets_backend': [
            'custom_homepage/static/src/scss/homepage.scss',
            'custom_homepage/static/src/js/homepage.js',
        ],
        'web.assets_frontend': [
            'custom_homepage/static/src/scss/homepage.scss',
            'custom_homepage/static/src/js/homepage.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': True,
}