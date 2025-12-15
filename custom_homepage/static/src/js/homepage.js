/* static/src/js/homepage.js */

odoo.define('custom_homepage.homepage', function (require) {
    'use strict';

    var core = require('web.core');
    var publicWidget = require('web.public.widget');
    
    // Homepage Widget
    publicWidget.registry.CustomHomepage = publicWidget.Widget.extend({
        selector: '.custom-homepage',
        events: {
            'click .module-card': '_onModuleClick',
        },

        /**
         * @override
         */
        start: function () {
            this._super.apply(this, arguments);
            this._initializeHomepage();
        },

        /**
         * Initialize homepage functionality
         */
        _initializeHomepage: function () {
            // Add loading animation
            this._addLoadingAnimation();
            
            // Initialize module cards
            this._initializeModuleCards();
            
            // Add welcome animation
            this._addWelcomeAnimation();
        },

        /**
         * Add loading animation to module cards
         */
        _addLoadingAnimation: function () {
            var self = this;
            this.$('.module-card').each(function (index) {
                $(this).css({
                    'opacity': '0',
                    'transform': 'translateY(50px)'
                });
                
                setTimeout(function () {
                    $(this).animate({
                        'opacity': '1',
                        'transform': 'translateY(0px)'
                    }, 500);
                }.bind(this), index * 100);
            });
        },

        /**
         * Initialize module card interactions
         */
        _initializeModuleCards: function () {
            var self = this;
            
            // Add hover effects
            this.$('.module-card').hover(
                function () {
                    $(this).find('.module-icon i').addClass('fa-spin');
                },
                function () {
                    $(this).find('.module-icon i').removeClass('fa-spin');
                }
            );

            // Add click ripple effect
            this.$('.module-card').on('mousedown', function (e) {
                var card = $(this);
                var ripple = $('<div class="ripple"></div>');
                var rect = this.getBoundingClientRect();
                var size = Math.max(rect.width, rect.height);
                var x = e.clientX - rect.left - size / 2;
                var y = e.clientY - rect.top - size / 2;
                
                ripple.css({
                    position: 'absolute',
                    borderRadius: '50%',
                    background: 'rgba(255, 255, 255, 0.6)',
                    transform: 'scale(0)',
                    left: x + 'px',
                    top: y + 'px',
                    width: size + 'px',
                    height: size + 'px',
                    pointerEvents: 'none',
                    animation: 'ripple-animation 0.6s linear'
                });
                
                card.append(ripple);
                
                setTimeout(function () {
                    ripple.remove();
                }, 600);
            });
        },

        /**
         * Add welcome animation
         */
        _addWelcomeAnimation: function () {
            var welcomeText = this.$('.homepage-header h1');
            var leadText = this.$('.homepage-header .lead');
            
            // Typewriter effect for welcome text
            var text = welcomeText.text();
            welcomeText.text('');
            
            var i = 0;
            var typeWriter = function () {
                if (i < text.length) {
                    welcomeText.text(welcomeText.text() + text.charAt(i));
                    i++;
                    setTimeout(typeWriter, 100);
                } else {
                    // Show lead text after welcome text is complete
                    leadText.fadeIn(500);
                }
            };
            
            leadText.hide();
            setTimeout(typeWriter, 500);
        },

        /**
         * Handle module card click
         */
        _onModuleClick: function (ev) {
            ev.preventDefault();
            var $card = $(ev.currentTarget);
            var action = $card.data('action');
            
            if (action) {
                // Add loading state
                $card.addClass('loading');
                $card.find('.btn').html('<i class="fa fa-spinner fa-spin"></i> Loading...');
                
                // Add visual feedback
                $card.css('transform', 'scale(0.95)');
                
                setTimeout(function () {
                    window.location.href = action;
                }, 300);
            }
        },
    });

    // Add custom CSS animations
    $('<style>')
        .prop('type', 'text/css')
        .html(`
            @keyframes ripple-animation {
                to {
                    transform: scale(4);
                    opacity: 0;
                }
            }
            
            .module-card.loading {
                opacity: 0.7;
                pointer-events: none;
            }
            
            .module-card .fa-spin {
                animation: fa-spin 1s infinite linear;
            }
        `)
        .appendTo('head');

    return publicWidget.registry.CustomHomepage;
});

// Alternative vanilla JavaScript implementation for broader compatibility
document.addEventListener('DOMContentLoaded', function() {
    // Only execute if we're on the custom homepage
    if (!document.querySelector('.custom-homepage')) {
        return;
    }

    /**
     * Initialize homepage functionality
     */
    function initializeHomepage() {
        addModuleCardListeners();
        addQuickActionListeners();
        addKeyboardNavigation();
    }

    /**
     * Add event listeners to module cards
     */
    function addModuleCardListeners() {
        var moduleCards = document.querySelectorAll('.module-card');
        
        moduleCards.forEach(function(card) {
            card.addEventListener('click', function(e) {
                e.preventDefault();
                var action = this.getAttribute('data-action');
                
                if (action) {
                    // Visual feedback
                    this.style.transform = 'scale(0.95)';
                    var btn = this.querySelector('.btn');
                    btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Loading...';
                    
                    // Navigate after animation
                    setTimeout(function() {
                        window.location.href = action;
                    }, 200);
                }
            });

            // Add keyboard support
            card.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    this.click();
                }
            });
        });
    }

    /**
     * Add event listeners to quick action buttons
     */
    function addQuickActionListeners() {
        var quickActions = document.querySelectorAll('.btn-outline-secondary');
        
        quickActions.forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                // Add loading state
                var originalText = this.innerHTML;
                this.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Loading...';
                this.style.pointerEvents = 'none';
                
                // Reset after a delay if navigation fails
                setTimeout(function() {
                    this.innerHTML = originalText;
                    this.style.pointerEvents = 'auto';
                }.bind(this), 3000);
            });
        });
    }

    /**
     * Add keyboard navigation support
     */
    function addKeyboardNavigation() {
        var focusableElements = document.querySelectorAll('.module-card, .btn-outline-secondary');
        
        // Make module cards focusable
        document.querySelectorAll('.module-card').forEach(function(card) {
            card.setAttribute('tabindex', '0');
            card.setAttribute('role', 'button');
            card.setAttribute('aria-label', 'Open ' + card.querySelector('.card-title span').textContent + ' module');
        });

        // Add arrow key navigation
        document.addEventListener('keydown', function(e) {
            var focused = document.activeElement;
            var index = Array.from(focusableElements).indexOf(focused);
            
            if (index === -1) return;
            
            var next;
            switch(e.key) {
                case 'ArrowRight':
                case 'ArrowDown':
                    e.preventDefault();
                    next = (index + 1) % focusableElements.length;
                    focusableElements[next].focus();
                    break;
                case 'ArrowLeft':
                case 'ArrowUp':
                    e.preventDefault();
                    next = (index - 1 + focusableElements.length) % focusableElements.length;
                    focusableElements[next].focus();
                    break;
            }
        });
    }

    function click(params) {
        console.log(this);
        
    }

    // Initialize the homepage
    initializeHomepage();
});