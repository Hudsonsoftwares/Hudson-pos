/* eslint-disable */
(function (global) {
    'use strict';

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
    
    function generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            var r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }
    
    function getToken() { return document.body.getAttribute('data-station-token'); }
    function authHeaders() {
        var token = getToken();
        return token ? { 'X-EH-Kiosk-Token': token } : {};
    }
    function postJson(url, body, headers) {
        var hdrs = Object.assign({ 'Content-Type': 'application/json' }, headers || {});
        return fetch(url, { method: 'POST', headers: hdrs, body: JSON.stringify(body || {}) })
            .then(function (r) { return r.json().then(function (j) { return { status: r.status, body: j }; }); });
    }
    function getJson(url, headers) {
        return fetch(url, { method: 'GET', headers: headers || {} })
            .then(function (r) { return r.json().then(function (j) { return { status: r.status, body: j }; }); });
    }

    function loadBootstrap() {
        var token = getToken();
        return getJson('/fd/kiosk/bootstrap/' + token, authHeaders()).then(function (res) {
            if (res.status !== 200) {
                alert('Station unauthorized or inactive.');
                return;
            }
            bootstrap = res.body;
            setupUI();
        });
    }

    function setupUI() {
        // Purposes
        var purSel = $('#eh-vis-purpose');
        purSel.innerHTML = '';
        var placeholderOpt = document.createElement('option');
        placeholderOpt.value = '';
        placeholderOpt.textContent = 'Select a purpose...';
        placeholderOpt.disabled = true;
        placeholderOpt.selected = true;
        purSel.appendChild(placeholderOpt);
        (bootstrap.purposes || []).forEach(function (p) {
            var o = document.createElement('option');
            o.value = p.id; o.textContent = p.name;
            purSel.appendChild(o);
        });

        // Configurable fields
        if (bootstrap.field_email !== 'hidden') {
            $('#eh-vis-email-container').classList.remove('eh-hidden');
            if (bootstrap.field_email === 'required') $('#eh-vis-email-label').textContent = 'Email *';
        }
        if (bootstrap.field_phone !== 'hidden') {
            $('#eh-vis-phone-container').classList.remove('eh-hidden');
            if (bootstrap.field_phone === 'required') $('#eh-vis-phone-label').textContent = 'Phone *';
        }
        if (bootstrap.field_organization !== 'hidden') {
            $('#eh-vis-company-container').classList.remove('eh-hidden');
            if (bootstrap.field_organization === 'required') $('#eh-vis-company-label').textContent = 'Organization *';
        }

        if (bootstrap.host_selection) {
            $('#eh-vis-host-container').classList.remove('eh-hidden');
            wireHostDirectory();
        }

        if (bootstrap.self_checkin) {
            $('#eh-home-qr').classList.remove('eh-hidden');
            var cleanUrl = window.location.origin + window.location.pathname;
            $('#eh-home-qr-img').src = '/report/barcode/QR/' + encodeURIComponent(cleanUrl) + '?width=400&height=400';
        }


        var companyNameEl = $('#eh-company-name-display');
        if (companyNameEl && bootstrap.company_name) {
            companyNameEl.textContent = bootstrap.company_name;
        }
        // Update company name on light-theme logo spans
        var logoSpans = document.querySelectorAll('[id^="eh-logo-company-name"]');
        logoSpans.forEach(function(el) { el.textContent = bootstrap.company_name || ''; });

        startClock();
    }

    function startClock() {
        var timeEl = $('#eh-clock-time');
        if (!timeEl) return;

        function updateClock() {
            var now = new Date();
            var hours = now.getHours();
            var minutes = now.getMinutes();
            var ampm = hours >= 12 ? 'PM' : 'AM';
            hours = hours % 12;
            hours = hours ? hours : 12;
            minutes = minutes < 10 ? '0' + minutes : minutes;
            timeEl.textContent = hours + ':' + minutes + ' ' + ampm;
        }
        updateClock();
        setInterval(updateClock, 1000);
    }

    function wireHostDirectory() {
        var btnBrowse = $('#btn-browse-hosts');
        var btnBack = $('#btn-hosts-back');
        var searchInput = $('#host-search-input');
        var filterDept = $('#host-filter-dept');
        var filterCompany = $('#host-filter-company');
        var grid = $('#hosts-grid');
        var empty = $('#hosts-empty');
        var hiddenHost = $('#eh-vis-host');
        var selectedDisplay = $('#selected-host-display');
        var selectedAvatar = $('#selected-host-avatar');
        var selectedName = $('#selected-host-name');
        var selectedJob = $('#selected-host-job');
        var purposeInput = $('#eh-vis-purpose');
        var nextBtn = $('#eh-step2-next');

        if (!btnBrowse || !grid) return;

        // Populate filters
        var depts = new Set();
        var companies = new Set();
        (window.ehAllHosts || []).forEach(function(h) {
            if (h.department) depts.add(h.department);
            if (h.company) companies.add(h.company);
        });
        
        Array.from(depts).sort().forEach(function(d) {
            var opt = document.createElement('option');
            opt.value = d; opt.textContent = d;
            filterDept.appendChild(opt);
        });
        Array.from(companies).sort().forEach(function(c) {
            var opt = document.createElement('option');
            opt.value = c; opt.textContent = c;
            filterCompany.appendChild(opt);
        });

        function validateStep2() {
            var hasHost = !!hiddenHost.value;
            var hasPurpose = !!purposeInput.value;
            if (nextBtn) {
                nextBtn.disabled = !(hasHost && hasPurpose);
            }
        }

        if (purposeInput) {
            purposeInput.addEventListener('change', validateStep2);
        }

        function renderHosts() {
            grid.innerHTML = '';
            var q = (searchInput.value || '').toLowerCase().trim();
            var d = filterDept.value;
            var c = filterCompany.value;
            
            var count = 0;
            (window.ehAllHosts || []).forEach(function(h) {
                if (d && h.department !== d) return;
                if (c && h.company !== c) return;
                if (q) {
                    var match = ((h.name || '').toLowerCase().indexOf(q) > -1) ||
                                ((h.job_title || '').toLowerCase().indexOf(q) > -1) ||
                                ((h.department || '').toLowerCase().indexOf(q) > -1);
                    if (!match) return;
                }
                
                count++;
                
                var card = document.createElement('div');
                card.className = 'host-card';
                card.innerHTML = `
                    <img src="${h.avatar}" class="host-avatar" onerror="this.src='data:image/svg+xml;utf8,<svg fill=%22%23ccc%22 viewBox=%220 0 24 24%22 xmlns=%22http://www.w3.org/2000/svg%22><path d=%22M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z%22/></svg>'" />
                    <div class="host-info">
                        <div class="host-name">${h.name}</div>
                        ${h.job_title ? '<div class="host-job">' + h.job_title + '</div>' : ''}
                        <div class="host-meta">
                            ${h.department ? '<span class="host-meta-item">' + h.department + '</span>' : ''}
                            ${h.company ? '<span class="host-meta-item">' + h.company + '</span>' : ''}
                        </div>
                    </div>
                `;
                
                card.addEventListener('click', function() {
                    hiddenHost.value = h.id;
                    selectedName.textContent = h.name;
                    selectedJob.textContent = h.job_title || '';
                    selectedAvatar.src = h.avatar;
                    
                    btnBrowse.classList.add('eh-hidden');
                    selectedDisplay.classList.remove('eh-hidden');
                    
                    validateStep2();
                    show('step2');
                });
                
                grid.appendChild(card);
            });
            
            if (count === 0) {
                empty.classList.remove('eh-hidden');
            } else {
                empty.classList.add('eh-hidden');
            }
        }

        btnBrowse.addEventListener('click', function() {
            searchInput.value = '';
            filterDept.value = '';
            filterCompany.value = '';
            renderHosts();
            show('hosts');
        });

        selectedDisplay.addEventListener('click', function() {
            renderHosts();
            show('hosts');
        });

        btnBack.addEventListener('click', function() {
            show('step2');
        });

        searchInput.addEventListener('input', renderHosts);
        filterDept.addEventListener('change', renderHosts);
        filterCompany.addEventListener('change', renderHosts);
        
        // Initial validate
        validateStep2();
    }

    function startSignIn() {
        draft = {};
        draft.transaction_id = generateUUID();
        show('step1');
    }

    function continueFromStep1() {
        draft.name = ($('#eh-vis-name').value || '').trim();
        draft.visitor_company = ($('#eh-vis-company').value || '').trim();
        draft.visitor_email = ($('#eh-vis-email').value || '').trim();
        draft.visitor_phone = ($('#eh-vis-phone').value || '').trim();

        if (!draft.name) { alert('Name is required.'); return; }
        if (!draft.visitor_phone) { alert('Phone is required.'); return; }
        
        // We still validate these if they somehow get enabled by backend config, but phone is always required now.
        if (bootstrap.field_email === 'required' && !draft.visitor_email) { alert('Email is required.'); return; }
        if (bootstrap.field_organization === 'required' && !draft.visitor_company) { alert('Organization is required.'); return; }

        show('step2');
    }

    function continueFromStep2() {
        var purposeId = parseInt($('#eh-vis-purpose').value, 10);
        var purpose = (bootstrap.purposes || []).find(function (p) { return p.id === purposeId; });
        
        draft.host_id = parseInt($('#eh-vis-host').value, 10);
        draft.purpose_id = purposeId;
        draft.nda_required = !!(purpose && purpose.nda_required);
        draft.photo_required = !!(purpose && purpose.photo_required);
        draft.nda_accepted = false;
        draft.photo_b64 = null;
        draft.drink_id = null;

        if (bootstrap.host_selection && !draft.host_id) { alert('Please select a host.'); return; }
        if (!draft.purpose_id) { alert('Purpose is required.'); return; }

        gotoNda();
    }


    function gotoNda() {
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
        gotoPhoto();
    }

    function continueFromNda() {
        if (!$('#eh-nda-accept').checked) { alert('Please accept the terms.'); return; }
        if (signaturePad && signaturePad.isEmpty()) { alert('Please provide your signature.'); return; }
        
        draft.nda_accepted = true;
        if (signaturePad) {
            draft.digital_signature_b64 = signaturePad.toDataURL('image/png');
        }
        gotoPhoto();
    }

    function gotoPhoto() {
        if (draft.photo_required) {
            $('#eh-photo-consent').textContent = bootstrap.photo_consent_text || '';
            show('photo');
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                alert('Camera not supported on this device. Skipping photo.');
                stopPhoto();
                gotoFinal();
                return;
            }
            navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false }).then(function (stream) {
                photoStream = stream;
                $('#eh-photo-video').srcObject = stream;
            }).catch(function () {
                alert('Camera access denied. Skipping photo.');
                stopPhoto();
                gotoFinal();
            });
            return;
        }
        gotoFinal();
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
        gotoFinal();
    }

    function stopPhoto() {
        if (photoStream) {
            photoStream.getTracks().forEach(function (t) { t.stop(); });
            photoStream = null;
        }
    }

    var autoSubmitTimer = null;

    function gotoFinal() {
        // Populate host name
        var hostName = '';
        if (draft.host_id) {
            var host = (window.ehAllHosts || []).find(function(h) { return h.id === draft.host_id; });
            if (host) hostName = host.name;
        }
        var subtitle = $('#eh-final-subtitle');
        if (subtitle) {
            if (hostName) {
                subtitle.textContent = 'Please have a seat. ' + hostName + ' will get back to you.';
            } else {
                subtitle.textContent = 'Please have a seat. Someone will get back to you shortly.';
            }
        }

        // Populate side message
        var sideMsgContainer = $('#eh-final-side-message-container');
        var sideMsg = $('#eh-final-side-message');
        if (bootstrap.side_message) {
            sideMsg.innerHTML = bootstrap.side_message;
            sideMsgContainer.style.display = 'block';
        } else {
            sideMsgContainer.style.display = 'none';
        }

        // Drinks Logic
        var drinksSection = $('#eh-final-drinks-section');
        var drinksPrompt = $('#eh-final-drinks-prompt');
        var drinksGrid = $('#eh-final-drinks-grid');
        
        if (bootstrap.offer_drinks && bootstrap.drinks && bootstrap.drinks.length) {
            drinksSection.classList.remove('eh-hidden');
            drinksPrompt.style.display = 'flex';
            drinksGrid.classList.add('eh-hidden');
            
            var gridEl = $('#eh-drinks-grid');
            if (gridEl) {
                gridEl.innerHTML = '';
                bootstrap.drinks.forEach(function(d) {
                    var btn = document.createElement('div');
                    btn.className = 'eh-drink-card';
                    btn.style.width = '180px';
                    btn.style.padding = '20px';
                    btn.style.border = '1px solid #eaeaea';
                    btn.style.borderRadius = '8px';
                    btn.style.cursor = 'pointer';
                    btn.style.display = 'flex';
                    btn.style.flexDirection = 'column';
                    btn.style.alignItems = 'center';
                    btn.style.background = '#fff';
                    
                    var img = document.createElement('img');
                    img.src = '/web/image/eh.hr.visitor.drink/' + d.id + '/image';
                    img.style.width = '100px';
                    img.style.height = '100px';
                    img.style.objectFit = 'contain';
                    img.style.marginBottom = '20px';
                    img.onerror = function() { this.style.display = 'none'; };
                    
                    var label = document.createElement('div');
                    label.textContent = d.name;
                    label.style.fontSize = '18px';
                    label.style.color = '#333';
                    
                    btn.appendChild(img);
                    btn.appendChild(label);
                    
                    btn.dataset.id = d.id;
                    btn.addEventListener('click', function() {
                        document.querySelectorAll('.eh-drink-card').forEach(function(c) { 
                            c.classList.remove('selected');
                            c.style.borderColor = '#eaeaea';
                            c.style.boxShadow = 'none';
                        });
                        btn.classList.add('selected');
                        btn.style.borderColor = '#7A557A';
                        btn.style.boxShadow = '0 0 0 2px #7A557A';
                        draft.drink_id = d.id;
                        draft.drink_name = d.name;
                        
                        var btnNothing = $('#btn-final-nothing');
                        if (btnNothing) {
                            btnNothing.textContent = 'Confirm Drink';
                            btnNothing.style.backgroundColor = '#7A557A';
                            btnNothing.style.color = '#fff';
                        }
                        
                        // Reset timer to give them more time after a click
                        clearTimeout(autoSubmitTimer);
                        autoSubmitTimer = setTimeout(function() {
                            if ($('.eh-screen-final:not(.eh-hidden)')) submit();
                        }, 30000);
                    });
                    gridEl.appendChild(btn);
                });
            }
        } else {
            drinksSection.classList.add('eh-hidden');
        }

        show('final');

        // Start 30s auto-submit timer (give them time to read and choose)
        clearTimeout(autoSubmitTimer);
        autoSubmitTimer = setTimeout(function() {
            if ($('.eh-screen-final:not(.eh-hidden)')) {
                submit();
            }
        }, 30000);
    }

    var isSubmitting = false;

    function submit() {
        if (isSubmitting) return;
        
        clearTimeout(autoSubmitTimer);
        var token = getToken();

        // Prevent duplicate submissions and update UI
        isSubmitting = true;
        
        var btnNothing = $('#btn-final-nothing');
        if (btnNothing) {
            btnNothing.disabled = true;
            btnNothing.textContent = "Processing check-in...";
            btnNothing.style.opacity = '0.7';
            btnNothing.style.cursor = 'wait';
        }
        
        var btnYes = $('#btn-drink-yes');
        var btnNo = $('#btn-drink-no');
        var btnClose = $('#btn-final-close');
        if (btnYes) btnYes.disabled = true;
        if (btnNo) btnNo.disabled = true;
        if (btnClose) btnClose.disabled = true;

        // Sanitise host_id: parseInt on an empty string returns NaN,
        // which JSON.stringify encodes as null — causing a 400 from the
        // backend. Normalise to null explicitly.
        var hostId = (draft.host_id && !isNaN(draft.host_id)) ? draft.host_id : null;

        var body = {
            transaction_id: draft.transaction_id,
            name: draft.name,
            visitor_company: draft.visitor_company,
            visitor_email: draft.visitor_email,
            visitor_phone: draft.visitor_phone,
            host_id: hostId,
            purpose_id: draft.purpose_id,
            nda_accepted: draft.nda_accepted,
            digital_signature_b64: draft.digital_signature_b64,
            photo_b64: draft.photo_b64,
            drink_id: draft.drink_id || null
        };

        postJson('/fd/kiosk/sign_in/' + token, body, {}).then(function (res) {
            isSubmitting = false;
            
            // Re-enable buttons if there was an error so they can try again
            if (res.status !== 200) {
                if (btnNothing) {
                    btnNothing.disabled = false;
                    btnNothing.textContent = draft.drink_id ? "Confirm Drink" : "No Thanks / Nothing";
                    btnNothing.style.opacity = '1';
                    btnNothing.style.cursor = 'pointer';
                }
                if (btnYes) btnYes.disabled = false;
                if (btnNo) btnNo.disabled = false;
                if (btnClose) btnClose.disabled = false;
            }
            if (res.status !== 200) {
                // Show a user-visible error and stay on the current screen
                // rather than silently discarding the sign-in and going home.
                var errMsg = (res.body && res.body.error) || 'Check-in failed. Please try again.';
                console.error('Sign-in failed:', res.body);
                alert(errMsg);
                return;
            }

            // ── Resolve host name ────────────────────────────────────────
            var hostName = (res.body && res.body.host_name) || '';
            if (!hostName) {
                var hostObj = (window.ehAllHosts || []).find(function(h) { return h.id == draft.host_id; });
                if (hostObj) hostName = hostObj.name;
            }

            // ── Resolve purpose name ─────────────────────────────────────
            var purposeName = '';
            var purposeObj = (bootstrap.purposes || []).find(function(p) { return p.id == draft.purpose_id; });
            if (purposeObj) purposeName = purposeObj.name;

            // ── Format check-in time ─────────────────────────────────────
            var now = new Date();
            var hours = now.getHours();
            var minutes = now.getMinutes();
            var ampm = hours >= 12 ? 'PM' : 'AM';
            hours = hours % 12 || 12;
            var timeStr = hours + ':' + (minutes < 10 ? '0' + minutes : minutes) + ' ' + ampm;
            var dateStr = now.toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

            // ── Populate success screen ──────────────────────────────────
            var elVisitorName = $('#eh-success-visitor-name');
            if (elVisitorName) elVisitorName.textContent = draft.name || '';

            var elHostName = $('#eh-success-host-name');
            if (elHostName) elHostName.textContent = hostName || 'Your host';

            var elPurpose = $('#eh-success-purpose');
            if (elPurpose) elPurpose.textContent = purposeName || '';

            var elDrink = $('#eh-success-drink');
            var elDrinkRow = $('#eh-success-drink-row');
            if (draft.drink_id && draft.drink_name) {
                if (elDrink) elDrink.textContent = draft.drink_name;
                if (elDrinkRow) elDrinkRow.classList.remove('eh-hidden');
            } else {
                if (elDrinkRow) elDrinkRow.classList.add('eh-hidden');
            }

            var elTime = $('#eh-success-checkin-time');
            if (elTime) elTime.textContent = timeStr + '  ·  ' + dateStr;

            var elNotified = $('#eh-success-notified');
            if (elNotified) {
                if (draft.drink_id && draft.drink_name) {
                    elNotified.textContent = 'Your ' + draft.drink_name.toLowerCase() + ' is on the way. Your host has been notified.';
                } else {
                    elNotified.textContent = 'Your host has been notified.';
                }
            }

            // Side message
            var sideContainer = $('#eh-success-side-message-container');
            var sideMessage = $('#eh-success-side-message');
            if (bootstrap.side_message) {
                if (sideContainer) sideContainer.classList.remove('eh-hidden');
                if (sideMessage) sideMessage.innerHTML = bootstrap.side_message;
            } else {
                if (sideContainer) sideContainer.classList.add('eh-hidden');
            }

            // Navigate to the dedicated success screen
            show('success');

            // "Close" button: manual early dismiss
            var btnClose = $('#btn-success-close');
            if (btnClose) {
                btnClose.onclick = function() {
                    show('home');
                    clearForm();
                };
            }

            // Auto-redirect to Welcome after 8 seconds
            setTimeout(function() {
                var successScreen = $('.eh-screen-success');
                if (successScreen && !successScreen.classList.contains('eh-hidden')) {
                    show('home');
                    clearForm();
                }
            }, 8000);

        }).catch(function(err) {
            console.error('Sign-in network/parse error:', err);
            alert('Network error: ' + (err.message || err) + '. Please try again.');
        });
    }

    function clearForm() {
        $('#eh-vis-name').value = '';
        $('#eh-vis-email').value = '';
        $('#eh-vis-phone').value = '';
        $('#eh-vis-company').value = '';
        
        var hiddenHost = $('#eh-vis-host');
        if (hiddenHost) hiddenHost.value = '';
        
        var btnBrowse = $('#btn-browse-hosts');
        var selectedDisplay = $('#selected-host-display');
        var nextBtn = $('#eh-step2-next');
        
        if (btnBrowse && selectedDisplay) {
            btnBrowse.classList.remove('eh-hidden');
            selectedDisplay.classList.add('eh-hidden');
        }
        
        if (nextBtn) {
            nextBtn.disabled = true;
        }
        
        var purSel = $('#eh-vis-purpose');
        if (purSel) {
            purSel.value = '';
        }
    }

    function init() {
        if (!getToken()) return; // Not a station URL
        loadBootstrap().then(function () {
            show('home');
            $('#eh-home-signin').addEventListener('click', startSignIn);
            $('#eh-step1-next').addEventListener('click', continueFromStep1);
            $('#eh-step1-back').addEventListener('click', function () { show('home'); });
            $('#eh-step2-next').addEventListener('click', continueFromStep2);
            $('#eh-step2-back').addEventListener('click', function () { show('step1'); });
            
            var btnYes = $('#btn-drink-yes');
            if (btnYes) btnYes.addEventListener('click', function() {
                $('#eh-final-drinks-prompt').style.display = 'none';
                $('#eh-final-drinks-grid').classList.remove('eh-hidden');
                
                $('#eh-final-title').classList.add('eh-hidden');
                $('#eh-final-subtitle').classList.add('eh-hidden');
                $('#eh-final-drink-question').classList.add('eh-hidden');
                $('#eh-final-delight-title').classList.remove('eh-hidden');
                $('#btn-final-close').classList.add('eh-hidden');
                $('#btn-final-nothing').classList.remove('eh-hidden');
                
                clearTimeout(autoSubmitTimer);
                autoSubmitTimer = setTimeout(function() {
                    if ($('.eh-screen-final:not(.eh-hidden)')) submit();
                }, 30000);
            });

            var btnNo = $('#btn-drink-no');
            if (btnNo) btnNo.addEventListener('click', function() {
                clearTimeout(autoSubmitTimer);
                draft.drink_id = null;
                submit();
            });

            var btnClose = $('#btn-final-close');
            if (btnClose) btnClose.addEventListener('click', function() {
                clearTimeout(autoSubmitTimer);
                submit();
            });

            var btnNothing = $('#btn-final-nothing');
            if (btnNothing) btnNothing.addEventListener('click', function() {
                clearTimeout(autoSubmitTimer);
                if (btnNothing.textContent.indexOf('Nothing') !== -1) {
                    draft.drink_id = null;
                }
                submit();
            });
            var ndaNext = $('#eh-nda-next');
            if (ndaNext) ndaNext.addEventListener('click', continueFromNda);
            var ndaBack = $('#eh-nda-back');
            if (ndaBack) ndaBack.addEventListener('click', function () { show('step2'); });
            
            var photoCap = $('#eh-photo-capture');
            if (photoCap) photoCap.addEventListener('click', capturePhoto);
            var photoSkip = $('#eh-photo-skip');
            if (photoSkip) photoSkip.addEventListener('click', function () { stopPhoto(); gotoFinal(); });
            
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
