/* eslint-disable */
/*
 * Visitor sign-in kiosk shell. Vanilla JS, no Odoo web framework
 * dependency. State machine:
 *
 *  pair -> home
 *  home + signin -> form -> nda? -> photo? -> result -> home
 *  home + signout -> signout -> home
 */
(function (global) {
    'use strict';

    var TOKEN_KEY = 'eh_kiosk_device_token_v1';
    var bootstrap = null;
    var draft = null;
    var photoStream = null;
    var signaturePad = null;

    function $(sel) { return document.querySelector(sel); }
    function show(screen) {
        document.querySelectorAll('.eh-screen').forEach(function (el) { el.classList.add('eh-hidden'); });
        var el = document.querySelector('.eh-screen[data-screen="' + screen + '"]');
        if (el) el.classList.remove('eh-hidden');
    }
    function getToken() { return localStorage.getItem(TOKEN_KEY); }
    function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }
    function clearToken() { localStorage.removeItem(TOKEN_KEY); }
    function authHeaders() { return { 'X-EH-Kiosk-Token': getToken() }; }

    function postJson(url, body, headers) {
        var hdrs = Object.assign({ 'Content-Type': 'application/json' }, headers || {});
        return fetch(url, { method: 'POST', headers: hdrs, body: JSON.stringify(body || {}) })
            .then(function (r) { return r.json().then(function (j) { return { status: r.status, body: j }; }); });
    }
    function getJson(url, headers) {
        return fetch(url, { method: 'GET', headers: headers || {} })
            .then(function (r) { return r.json().then(function (j) { return { status: r.status, body: j }; }); });
    }

    function doPair() {
        var siteCode = document.body.getAttribute('data-site-code');
        var name = ($('#eh-pair-name').value || '').trim() || 'Reception';
        var pin = ($('#eh-pair-pin').value || '').trim();
        var errEl = $('#eh-pair-error');
        if (!pin) { errEl.textContent = 'Enter pairing PIN.'; return; }
        postJson('/eh_hr/kiosk/pair', { site_code: siteCode, pin: pin, device_name: name }).then(function (res) {
            if (res.status !== 200) {
                errEl.textContent = (res.body && res.body.error) || 'Pairing failed';
                return;
            }
            setToken(res.body.device_token);
            loadBootstrap().then(function () { show('home'); });
        });
    }

    function loadBootstrap() {
        return getJson('/eh_hr/visitor/bootstrap', authHeaders()).then(function (res) {
            if (res.status !== 200) {
                clearToken();
                show('pair');
                return;
            }
            bootstrap = res.body;
            populateSelects();
        });
    }

    function populateSelects() {
        // Hosts are no longer dumped in the bootstrap payload (that leaked the
        // whole employee directory to any device-token holder). They are
        // resolved on demand via a throttled typeahead, see wireHostSearch().
        var purSel = $('#eh-vis-purpose');
        purSel.innerHTML = '';
        (bootstrap.purposes || []).forEach(function (p) {
            var o = document.createElement('option');
            o.value = p.id; o.textContent = p.name;
            purSel.appendChild(o);
        });
    }

    var _hostSearchTimer = null;
    function wireHostSearch() {
        var input = $('#eh-vis-host-search');
        var results = $('#eh-vis-host-results');
        var hidden = $('#eh-vis-host');
        if (!input || !results || !hidden) { return; }

        function clearResults() { results.innerHTML = ''; }

        function runSearch(q) {
            getJson('/eh_hr/visitor/host_search?q=' + encodeURIComponent(q), authHeaders())
                .then(function (res) {
                    clearResults();
                    var hosts = (res.body && res.body.hosts) || [];
                    hosts.forEach(function (h) {
                        var item = document.createElement('button');
                        item.type = 'button';
                        item.className = 'eh-host-option';
                        item.textContent = h.name;
                        item.addEventListener('click', function () {
                            hidden.value = h.id;
                            input.value = h.name;
                            clearResults();
                        });
                        results.appendChild(item);
                    });
                });
        }

        input.addEventListener('input', function () {
            hidden.value = '';  // typing invalidates a prior pick
            var q = (input.value || '').trim();
            if (_hostSearchTimer) { clearTimeout(_hostSearchTimer); }
            if (q.length < 2) { clearResults(); return; }
            _hostSearchTimer = setTimeout(function () { runSearch(q); }, 200);
        });
    }

    function startSignIn() {
        draft = {};
        show('form');
    }

    function continueFromForm() {
        var purposeId = parseInt($('#eh-vis-purpose').value, 10);
        var purpose = (bootstrap.purposes || []).find(function (p) { return p.id === purposeId; });
        draft = {
            name: ($('#eh-vis-name').value || '').trim(),
            visitor_company: ($('#eh-vis-company').value || '').trim(),
            visitor_email: ($('#eh-vis-email').value || '').trim(),
            host_id: parseInt($('#eh-vis-host').value, 10),
            purpose_id: purposeId,
            nda_required: !!(purpose && purpose.nda_required),
            photo_required: !!(purpose && purpose.photo_required),
            nda_accepted: false,
            photo_b64: null,
        };
        if (!draft.name || !draft.host_id || !draft.purpose_id) {
            alert('Name, host, and purpose are required.');
            return;
        }
        if (draft.nda_required) {
            $('#eh-nda-text').textContent = bootstrap.nda_text || '';
            $('#eh-nda-accept').checked = false;
            show('nda');
            // resize canvas
            setTimeout(function() {
                var canvas = document.getElementById('signature-pad');
                if (canvas) {
                    var ratio =  Math.max(window.devicePixelRatio || 1, 1);
                    canvas.width = canvas.offsetWidth * ratio;
                    canvas.height = canvas.offsetHeight * ratio;
                    canvas.getContext("2d").scale(ratio, ratio);
                    canvas.style.touchAction = 'none';
                    if (signaturePad) {
                        signaturePad.off();
                    }
                    if (typeof SignaturePad !== 'undefined') {
                        signaturePad = new SignaturePad(canvas, { backgroundColor: 'rgb(255, 255, 255)' });
                    }
                }
            }, 150);
            return;
        }
        if (draft.photo_required) {
            startPhoto();
            return;
        }
        submit();
    }

    function continueFromNda() {
        if (!$('#eh-nda-accept').checked) { alert('Please accept the terms.'); return; }
        if (signaturePad && signaturePad.isEmpty()) { alert('Please provide your signature.'); return; }
        
        draft.nda_accepted = true;
        if (signaturePad) {
            draft.digital_signature_b64 = signaturePad.toDataURL('image/png');
        }
        
        if (draft.photo_required) { startPhoto(); return; }
        submit();
    }

    function startPhoto() {
        $('#eh-photo-consent').textContent = bootstrap.photo_consent_text || '';
        show('photo');
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            alert('Camera not supported on this device. Skipping photo.');
            stopPhoto();
            submit();
            return;
        }
        navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false }).then(function (stream) {
            photoStream = stream;
            $('#eh-photo-video').srcObject = stream;
        }).catch(function () {
            alert('Camera access denied. Skipping photo.');
            stopPhoto();
            submit();
        });
    }

    function capturePhoto() {
        var video = $('#eh-photo-video');
        var canvas = $('#eh-photo-canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        var ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        draft.photo_b64 = canvas.toDataURL('image/png');
        stopPhoto();
        submit();
    }

    function stopPhoto() {
        if (photoStream) {
            photoStream.getTracks().forEach(function (t) { t.stop(); });
            photoStream = null;
        }
    }

    function submit() {
        var body = {
            name: draft.name,
            visitor_company: draft.visitor_company,
            visitor_email: draft.visitor_email,
            host_id: draft.host_id,
            purpose_id: draft.purpose_id,
            nda_accepted: draft.nda_accepted,
            digital_signature_b64: draft.digital_signature_b64,
            photo_b64: draft.photo_b64,
        };
        postJson('/eh_hr/visitor/sign_in', body, authHeaders()).then(function (res) {
            if (res.status !== 200) {
                alert((res.body && res.body.error) || 'Sign-in failed');
                return;
            }
            $('#eh-result-title').textContent = 'Welcome ' + draft.name;
            $('#eh-result-detail').textContent = 'Visit number: ' + res.body.visit_number;
            show('result');
        });
    }

    function startSignOut() {
        $('#eh-signout-number').value = '';
        $('#eh-signout-error').textContent = '';
        show('signout');
    }

    function submitSignOut() {
        var num = ($('#eh-signout-number').value || '').trim();
        if (!num) { $('#eh-signout-error').textContent = 'Enter your visit number'; return; }
        postJson('/eh_hr/visitor/sign_out', { visit_number: num }, authHeaders()).then(function (res) {
            if (res.status !== 200 || !res.body || !res.body.ok) {
                $('#eh-signout-error').textContent = 'Visit not found or already signed out';
                return;
            }
            $('#eh-result-title').textContent = 'Goodbye ' + (res.body.visitor_name || '');
            $('#eh-result-detail').textContent = 'Duration: ' + (res.body.duration_minutes || 0) + ' min';
            show('result');
        });
    }

    function init() {
        var siteFound = document.body.getAttribute('data-site-found') === 'true';
        if (!siteFound) { show('error'); return; }
        if (!getToken()) {
            show('pair');
            $('#eh-pair-submit').addEventListener('click', doPair);
            $('#eh-pair-pin').addEventListener('keydown', function (e) { if (e.key === 'Enter') doPair(); });
            return;
        }
        loadBootstrap().then(function () {
            show('home');
            wireHostSearch();
            $('#eh-home-signin').addEventListener('click', startSignIn);
            $('#eh-home-signout').addEventListener('click', startSignOut);
            $('#eh-form-next').addEventListener('click', continueFromForm);
            $('#eh-form-back').addEventListener('click', function () { show('home'); });
            $('#eh-nda-next').addEventListener('click', continueFromNda);
            $('#eh-nda-back').addEventListener('click', function () { show('form'); });
            $('#eh-photo-capture').addEventListener('click', capturePhoto);
            $('#eh-photo-skip').addEventListener('click', function () { stopPhoto(); submit(); });
            $('#eh-result-back').addEventListener('click', function () { show('home'); });
            $('#eh-signout-submit').addEventListener('click', submitSignOut);
            $('#eh-signout-back').addEventListener('click', function () { show('home'); });
            
            var clearBtn = document.getElementById('clear-signature');
            if (clearBtn) clearBtn.addEventListener('click', function() {
                if (signaturePad) signaturePad.clear();
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})(typeof window !== 'undefined' ? window : this);
