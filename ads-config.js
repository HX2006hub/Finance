/**
 * HelloInsights — Centralized Ad Manager (ads-config.js)
 * 
 * All ad slots are defined here. Toggle enabled/disabled per slot.
 * Supports: Google AdSense, Google AdX (via AdSense SDK), MGID
 * 
 * Usage:
 *   1. Set AD_ENABLED_MASTER = true when ads are approved
 *   2. Replace placeholder IDs with real ad network IDs
 *   3. Set individual slot.enabled = true to activate
 *   4. Pages just need <div class="ad-slot" data-ad-slot="xxx"></div>
 * 
 * API:
 *   window.AdConfig.toggle('slot-id', true/false)  — Enable/disable a slot
 *   window.AdConfig.getStatus()                     — View all slot statuses
 *   window.AdConfig.renderAll()                     — Re-render all ad slots
 */
(function() {
    'use strict';

    // ========================================
    // 📢 MASTER SWITCH — Set true after ad approval
    // ========================================
    var AD_ENABLED_MASTER = true;

    // ========================================
    // 🔑 Ad Network Credentials
    // ========================================
    var ADSENSE_CLIENT = 'ca-pub-XXXXXXXXXXXXXXXX';
    var MGID_SITE_ID = '1104797';

    // ========================================
    // 📍 Ad Slot Definitions
    // enabled: false by default — set true after approval
    // ========================================
    var SLOTS = {
        // --- Index Page ---
        'native-top': {
            enabled: true,
            network: 'mgid',         // adsense | adx | mgid
            type: 'native',
            pages: ['index'],
            adClient: ADSENSE_CLIENT,
            adSlot: 'XXXXXXXXXX',
            format: 'auto',
            label: 'Header Native Ad (728×90 / responsive)'
        },
        'banner-mid-1': {
            enabled: true,
            network: 'mgid',
            type: 'banner',
            pages: ['index'],
            adClient: ADSENSE_CLIENT,
            adSlot: 'XXXXXXXXXX',
            format: 'auto',
            label: 'Article Grid Banner 1 (after 3rd card)'
        },
        'banner-mid-2': {
            enabled: true,
            network: 'mgid',
            type: 'banner',
            pages: ['index'],
            adClient: ADSENSE_CLIENT,
            adSlot: 'XXXXXXXXXX',
            format: 'auto',
            label: 'Article Grid Banner 2 (after 6th card)'
        },
        'banner-bottom': {
            enabled: true,
            network: 'mgid',
            type: 'banner',
            pages: ['index'],
            adClient: ADSENSE_CLIENT,
            adSlot: 'XXXXXXXXXX',
            format: 'auto',
            label: 'Above Footer Banner'
        },
        'anchor': {
            enabled: false,
            network: 'mgid',
            type: 'anchor',
            pages: ['index'],
            adClient: ADSENSE_CLIENT,
            adSlot: 'XXXXXXXXXX',
            format: 'auto',
            label: 'Bottom Floating Anchor'
        },
        'interstitial': {
            enabled: false,
            network: 'mgid',
            type: 'interstitial',
            pages: ['index'],
            adClient: ADSENSE_CLIENT,
            adSlot: 'XXXXXXXXXX',
            format: 'auto',
            label: 'Page Turn Interstitial'
        },
        // --- Article Page ---
        'article-banner-top': {
            enabled: true,
            network: 'mgid',
            type: 'banner',
            pages: ['article'],
            adClient: ADSENSE_CLIENT,
            adSlot: 'XXXXXXXXXX',
            format: 'auto',
            label: 'Article Top Banner'
        },
        'article-banner-mid': {
            enabled: true,
            network: 'mgid',
            type: 'banner',
            pages: ['article'],
            adClient: ADSENSE_CLIENT,
            adSlot: 'XXXXXXXXXX',
            format: 'auto',
            label: 'Article Mid Banner'
        }
    };

    // ========================================
    // 🔧 MGID Widget Configuration
    // Maps slot IDs to MGID Widget IDs
    // Currently using one widget (2057384) for all positions.
    // To use separate widgets per position, create more in MGID dashboard
    // and replace the IDs below.
    // ========================================
    var MGID_WIDGETS = {
        'native-top': '2057384',
        'banner-mid-1': '2057384',
        'banner-mid-2': '2057384',
        'banner-bottom': '2057384',
        'article-banner-top': '2057384',
        'article-banner-mid': '2057384'
    };

    // ========================================
    // Detect Current Page
    // ========================================
    function getCurrentPage() {
        if (location.pathname.indexOf('/articles/') !== -1) return 'article';
        var path = location.pathname.split('/').pop() || 'index.html';
        if (path.indexOf('article') !== -1) return 'article';
        if (path.indexOf('category') !== -1) return 'category';
        return 'index';
    }

    // ========================================
    // Load AdSense SDK (only if AdSense slots are used)
    // ========================================
    var _sdkLoaded = false;
    function loadAdSenseSDK() {
        if (_sdkLoaded) return;
        if (ADSENSE_CLIENT.indexOf('XXXX') !== -1) return;
        _sdkLoaded = true;
        var sdk = document.createElement('script');
        sdk.async = true;
        sdk.src = 'https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=' + ADSENSE_CLIENT;
        sdk.crossOrigin = 'anonymous';
        document.head.appendChild(sdk);
    }

    // ========================================
    // Render All Ad Slots
    // ========================================
    function renderAll() {
        var page = getCurrentPage();
        var containers = document.querySelectorAll('[data-ad-slot]');
        for (var i = 0; i < containers.length; i++) {
            var el = containers[i];
            var slotKey = el.getAttribute('data-ad-slot');
            var slot = SLOTS[slotKey];
            if (!slot) {
                el.style.display = 'none';
                continue;
            }
            // Check if slot should show on this page
            if (slot.pages.indexOf(page) === -1) {
                el.style.display = 'none';
                continue;
            }
            // Check master + individual enabled
            if (!AD_ENABLED_MASTER || !slot.enabled) {
                el.style.display = 'none';
                el.setAttribute('data-ad-disabled', 'true');
                continue;
            }
            // Render based on network
            if (slot.network === 'adsense' || slot.network === 'adx') {
                renderAdSenseSlot(el, slot);
            }
            // MGID slots are rendered by renderMGIDWidgets() below
        }
        // MGID widgets
        renderMGIDWidgets(page);
    }

    function renderAdSenseSlot(el, slot) {
        if (el.getAttribute('data-ad-rendered') === 'true') return;
        el.setAttribute('data-ad-rendered', 'true');
        loadAdSenseSDK();
        var ins = document.createElement('ins');
        ins.className = 'adsbygoogle';
        ins.style.cssText = 'display:block';
        ins.setAttribute('data-ad-client', slot.adClient);
        ins.setAttribute('data-ad-slot', slot.adSlot);
        ins.setAttribute('data-ad-format', slot.format || 'auto');
        ins.setAttribute('data-full-width-responsive', 'true');
        el.appendChild(ins);
        try {
            (window.adsbygoogle = window.adsbygoogle || []).push({});
        } catch (e) {}
    }

    // ========================================
    // Render MGID Widgets (Simple JS format)
    // ========================================
    function renderMGIDWidgets(page) {
        if (!MGID_SITE_ID || MGID_SITE_ID.indexOf('XXXX') !== -1) return;

        var hasWidgets = false;
        for (var id in MGID_WIDGETS) {
            if (!MGID_WIDGETS.hasOwnProperty(id) || !MGID_WIDGETS[id]) continue;
            hasWidgets = true;
            break;
        }
        if (!hasWidgets) return;

        // Load MGID site script once (head loader)
        if (!document.querySelector('script[src*="jsc.mgid.com"]')) {
            var s = document.createElement('script');
            s.src = 'https://jsc.mgid.com/site/' + MGID_SITE_ID + '.js';
            s.async = true;
            document.head.appendChild(s);
        }

        // Render each MGID widget container
        for (var slotId in MGID_WIDGETS) {
            if (!MGID_WIDGETS.hasOwnProperty(slotId) || !MGID_WIDGETS[slotId]) continue;

            // Check if this slot is enabled for current page
            var slot = SLOTS[slotId];
            if (!slot || !AD_ENABLED_MASTER || !slot.enabled) continue;
            if (slot.pages.indexOf(page) === -1) continue;

            var el = document.querySelector('[data-ad-slot="' + slotId + '"]');
            if (!el) continue;
            // Reset display in case checkFill hid it before MGID loaded
            el.style.display = '';

            // Skip if already rendered
            if (el.querySelector('[data-type="_mgwidget"]')) continue;

            // Create MGID widget container div
            var div = document.createElement('div');
            div.setAttribute('data-type', '_mgwidget');
            div.setAttribute('data-widget-id', MGID_WIDGETS[slotId]);
            el.appendChild(div);
        }

        // Trigger MGID load
        try { (window._mgq = window._mgq || []).push(["_mgc.load"]); } catch(e) {}
    }

    // ========================================
    // Fill Detection: hide unfilled, show filled
    // ========================================
    function checkFill() {
        var containers = document.querySelectorAll('[data-ad-slot]');
        for (var i = 0; i < containers.length; i++) {
            var el = containers[i];
            if (el.getAttribute('data-ad-disabled') === 'true') continue;

            var iframe = el.querySelector('iframe');
            var ins = el.querySelector('ins.adsbygoogle');
            var hasSize = false;
            if (ins) {
                var rect = ins.getBoundingClientRect();
                hasSize = rect.height > 10;
            }
            var hasMGID = el.querySelector('[data-type="_mgwidget"]');
            var mgidIframe = hasMGID ? hasMGID.querySelector('iframe') : null;

            if (iframe || hasSize || (hasMGID && mgidIframe)) {
                // Ad is filled — show it
                el.classList.add('ad-visible');
                el.classList.remove('ad-hidden');
                el.style.display = '';
            } else if (hasMGID && !mgidIframe) {
                // MGID widget div exists but ad hasn't loaded yet
                // Keep container visible so MGID can render into it
                el.style.display = '';
                // Re-trigger MGID load in case it missed the first push
                try { (window._mgq = window._mgq || []).push(["_mgc.load"]); } catch(e) {}
            } else {
                // No ad content at all
                el.style.display = 'none';
                el.classList.add('ad-hidden');
                el.classList.remove('ad-visible');
            }
        }
    }

    // ========================================
    // Public API
    // ========================================
    window.AdConfig = {
        /**
         * Toggle a specific ad slot on/off
         * @param {string} slotId - The slot key (e.g. 'native-top')
         * @param {boolean} enabled - true to enable, false to disable
         */
        toggle: function(slotId, enabled) {
            if (SLOTS[slotId]) {
                SLOTS[slotId].enabled = !!enabled;
                console.log('[AdConfig] ' + slotId + ' → ' + (enabled ? 'ON' : 'OFF'));
                // Re-render if currently on page
                renderAll();
                setTimeout(checkFill, 2000);
            } else {
                console.warn('[AdConfig] Slot not found: ' + slotId);
            }
        },
        /**
         * Get status of all ad slots
         * @returns {Object} Slot status map
         */
        getStatus: function() {
            var status = {};
            for (var key in SLOTS) {
                if (!SLOTS.hasOwnProperty(key)) continue;
                status[key] = {
                    enabled: SLOTS[key].enabled,
                    network: SLOTS[key].network,
                    type: SLOTS[key].type,
                    pages: SLOTS[key].pages,
                    label: SLOTS[key].label
                };
            }
            status._master = AD_ENABLED_MASTER;
            return status;
        },
        /**
         * Enable all slots at once
         */
        enableAll: function() {
            for (var key in SLOTS) {
                if (SLOTS.hasOwnProperty(key)) SLOTS[key].enabled = true;
            }
            renderAll();
            setTimeout(checkFill, 2000);
        },
        /**
         * Disable all slots at once
         */
        disableAll: function() {
            for (var key in SLOTS) {
                if (SLOTS.hasOwnProperty(key)) SLOTS[key].enabled = false;
            }
            renderAll();
        },
        /**
         * Re-render all ad slots (for dynamic content)
         */
        renderAll: renderAll
    };

    // ========================================
    // Auto Init
    // ========================================
    function init() {
        renderAll();
        // Multi-round fill detection (SDK loading delay)
        setTimeout(checkFill, 1500);
        setTimeout(checkFill, 4000);
        setTimeout(checkFill, 8000);
        setTimeout(checkFill, 15000); // Final check for slow-loading MGID ads
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Log status on load
    console.log('[AdConfig] Loaded. Master: ' + (AD_ENABLED_MASTER ? 'ON' : 'OFF'));
    console.log('[AdConfig] MGID Site ID: ' + MGID_SITE_ID);
    console.log('[AdConfig] Use window.AdConfig.getStatus() to view slots');
    console.log('[AdConfig] Use window.AdConfig.toggle("slot-id", true) to enable');
})();
