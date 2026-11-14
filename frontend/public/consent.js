/* CRMEvent Consent Manager: primo script della pagina. Consent Mode v2 su "denied"; GA4, PostHog e Brevo bloccati finché l'utente non sceglie dal banner. */
(function () {
    window.dataLayer = window.dataLayer || [];
    function gtag() { window.dataLayer.push(arguments); }
    window.gtag = gtag;
    gtag('consent', 'default', {
        analytics_storage: 'denied', ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied',
        functionality_storage: 'granted', security_storage: 'granted', wait_for_update: 500
    });
    gtag('set', 'ads_data_redaction', true);
    gtag('js', new Date());
    gtag('config', 'G-PZK7J854DS', { send_page_view: false, anonymize_ip: true });
    window.Brevo = window.Brevo || [];
    window.__crmTrackers = { ga: 'blocked', posthog: 'blocked', brevo: 'blocked' };
    var PROD = /(^|\.)crmevent\.it$/.test(location.hostname);
    function add(src) { var s = document.createElement('script'); s.async = true; s.src = src; document.head.appendChild(s); }
    var L = {
        ga: function () {
            if (window.__crmTrackers.ga === 'loaded') return;
            if (location.hostname !== 'crmevent.it') { window.__crmTrackers.ga = 'allowed_host_skipped'; return; }
            window.__crmTrackers.ga = 'loaded';
            add('https://www.googletagmanager.com/gtag/js?id=G-PZK7J854DS');
        },
        brevo: function () {
            if (window.__crmTrackers.brevo === 'loaded') return;
            if (!PROD) { window.__crmTrackers.brevo = 'allowed_host_skipped'; return; }
            window.__crmTrackers.brevo = 'loaded';
            window.Brevo.unshift(['init', { client_key: 'k9vpo2b6t6r859eigzo79xki' }]);
            add('https://cdn.brevo.com/js/sdk-loader.js');
        },
        posthog: function () {
            if (window.__crmTrackers.posthog === 'loaded') return;
            window.__crmTrackers.posthog = 'loaded';
            !(function (t, e) { var o, n, p, r; e.__SV || ((window.posthog = e), (e._i = []), (e.init = function (i, s, a) { function g(t, e) { var o = e.split("."); 2 == o.length && ((t = t[o[0]]), (e = o[1])), (t[e] = function () { t.push([e].concat(Array.prototype.slice.call(arguments, 0))); }); } ((p = t.createElement("script")).type = "text/javascript"), (p.crossOrigin = "anonymous"), (p.async = !0), (p.src = s.api_host.replace(".i.posthog.com", "-assets.i.posthog.com") + "/static/array.js"), (r = t.getElementsByTagName("script")[0]).parentNode.insertBefore(p, r); var u = e; for (void 0 !== a ? (u = e[a] = []) : (a = "posthog"), u.people = u.people || [], u.toString = function (t) { var e = "posthog"; return "posthog" !== a && (e += "." + a), t || (e += " (stub)"), e; }, u.people.toString = function () { return u.toString(1) + ".people (stub)"; }, o = "init capture identify register reset opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing startSessionRecording stopSessionRecording get_distinct_id".split(" "), n = 0; n < o.length; n++) g(u, o[n]); e._i.push([i, s, a]); }), (e.__SV = 1)); })(document, window.posthog || []);
            window.posthog.init("phc_DbsPb39SRc8z3EiQ6Dhj6ikv4H4rTKcht9d4sZSesceP", {
                api_host: "https://ap.emergent.sh", person_profiles: "identified_only",
                session_recording: { recordCrossOriginIframes: true, capturePerformance: false }
            });
        }
    };
    window.__crmApplyConsent = function (c) {
        gtag('consent', 'update', {
            analytics_storage: c.analytics ? 'granted' : 'denied',
            ad_storage: c.marketing ? 'granted' : 'denied',
            ad_user_data: c.marketing ? 'granted' : 'denied',
            ad_personalization: c.marketing ? 'granted' : 'denied'
        });
        if (c.analytics) { L.ga(); L.posthog(); }
        if (c.marketing) { L.brevo(); }
    };
    function purge(res) {
        var h = location.hostname, p = h.split('.'), ds = ['', h, '.' + h];
        if (p.length > 2) ds.push('.' + p.slice(-2).join('.'));
        document.cookie.split('; ').forEach(function (c) {
            var n = c.split('=')[0];
            if (res.some(function (r) { return r.test(n); })) ds.forEach(function (d) {
                document.cookie = n + '=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/' + (d ? '; domain=' + d : '');
            });
        });
    }
    try {
        var st = JSON.parse(localStorage.getItem('crmevent_consent'));
        var fresh = st && st.choices && Date.now() - st.ts < 180 * 864e5;
        if (!fresh || !st.choices.analytics) purge([/^_ga/, /^_gid$/, /^ph_/]);
        if (!fresh || !st.choices.marketing) purge([/^sib_/, /^brevo/, /^_brevo/]);
        if (fresh) window.__crmApplyConsent(st.choices);
    } catch (e) {}
    window.addEventListener("error", function (e) { if (e.error instanceof DOMException && e.error.name === "DataCloneError" && e.message && e.message.includes("PerformanceServerTiming")) { e.stopImmediatePropagation(); e.preventDefault(); } }, true);
    if (!PROD) { var em = document.createElement('script'); em.src = 'https://assets.emergent.sh/scripts/emergent-main.js'; document.head.appendChild(em); }
})();
