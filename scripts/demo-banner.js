// AegisGate Demo - Persistent DEMO MODE Banner
// ===============================================
// This file is injected into every page via nginx sub_filter.
// It adds a clickable "DEMO MODE" badge in the top-right
// corner that shows additional information when clicked.

(function() {
    'use strict';

    // Don't add the banner if it's already there
    if (document.getElementById('demo-mode-banner')) return;

    // Create the banner element
    var banner = document.createElement('a');
    banner.id = 'demo-mode-banner';
    banner.className = 'demo-mode-banner';
    banner.href = '#';
    banner.title = 'Click for more information about this demo';
    banner.innerHTML = '<span class="demo-mode-banner-icon">🛡️</span>DEMO MODE';

    // Create the info panel (hidden by default)
    var info = document.createElement('div');
    info.id = 'demo-mode-info';
    info.className = 'demo-mode-info';
    info.innerHTML = [
        '<h3>About this Demo</h3>',
        '<p>This is a <strong>live, interactive demo</strong> of the AegisGate Security Platform.</p>',
        '<p><strong>What this demo IS:</strong></p>',
        '<ul>',
        '<li>Real AegisGate code (v3.3.0-beta.2)</li>',
        '<li>Pre-loaded sample threats and MCP tools</li>',
        '<li>Pre-run EU AI Act compliance scan</li>',
        '<li>Mock dashboard with 24h of activity</li>',
        '<li>Interactive playground with 12 test prompts</li>',
        '</ul>',
        '<p><strong>What this demo is NOT:</strong></p>',
        '<ul>',
        '<li>Not a production environment</li>',
        '<li>All data is synthetic</li>',
        '<li>No real LLM calls (uses mock upstream)</li>',
        '<li>State resets every 24 hours</li>',
        '</ul>',
        '<p><a href="https://aegisgatesecurity.io/" target="_blank">aegisgatesecurity.io</a> for production</p>'
    ].join('');

    // Toggle info on click
    banner.onclick = function(e) {
        e.preventDefault();
        info.classList.toggle('show');
        return false;
    };

    // Close info when clicking outside
    document.addEventListener('click', function(e) {
        if (info.classList.contains('show') &&
            !info.contains(e.target) &&
            e.target !== banner &&
            !banner.contains(e.target)) {
            info.classList.remove('show');
        }
    });

    // Add to page when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            document.body.appendChild(banner);
            document.body.appendChild(info);
        });
    } else {
        document.body.appendChild(banner);
        document.body.appendChild(info);
    }
})();
