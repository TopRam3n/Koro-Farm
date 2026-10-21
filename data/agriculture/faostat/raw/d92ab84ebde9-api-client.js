/*global define, Q, amplify*/
define(['jquery', 'loglevel', 'q', 'globals/CognitoAuth', 'amplify'], function ($, log, Q, CognitoAuth) {

    'use strict';

    function FAOSTATAPIClient() {
        /* Store configuration. */

        this.CONFIG = {
            base_url: 'https://faostatservices.fao.org/api/v1/',
            guest_token_url: 'https://faostatservices.fao.org/api/v1/auth/guest',
            mode: 'prod',
            lang: 'en',
            log: false,
            use_auth_header: true
        };

        var isLocal = location.hostname.indexOf("localhost") !== -1 || location.hostname === "127.0.0.1" || location.hostname === "10.202.39.115" || location.hostname === "10.202.39.144";
        this.IS_LOCAL = isLocal;
        var isDevCloud = (location.href && location.href.indexOf("faostat.dev.aws.fao.org") !== -1) || (location.href && location.href.indexOf("faostat.fao.org/dev-internal/") !== -1);

        if (isDevCloud) {
            this.IS_DEV = true;
            this.CONFIG.base_url = 'https://api-faostat.dev.fao.org/api/v1/';
            this.CONFIG.guest_token_url = 'https://api-faostat.dev.fao.org/api/v1/auth/guest';
            this.CONFIG.log = true;
            this.CONFIG.datasource = "DEV_AWS";

            var modeName = isLocal ? "LOCAL DEV" : "CLOUD DEV";
            $('body').prepend('<div id="fs-debug-banner" class="alert alert-info fade in" role="alert" style="margin-bottom:0 !important; font-size:lager;">' + 'FAOSTAT is in <strong>' + modeName + '</strong> mode. Using <strong>' + (this.CONFIG.datasource || 'DEFAULT') + '</strong> datasource' + '</div>');
            console.log('FAOSTAT Configuration isDevCloud (' + modeName + '):', this.CONFIG);
        }

        if (isLocal) {
            this.IS_DEV = true;
            this.CONFIG.base_url = 'https://faostatservices-internal.fao.org/api/v1/';
            this.CONFIG.guest_token_url = 'https://faostatservices-internal.fao.org/api/v1/auth/guest';
            this.CONFIG.log = true;
            //this.CONFIG.datasource = "INTERNAL";
            var modeName = isLocal ? "LOCAL DEV" : "CLOUD DEV";
            $('body').prepend('<div id="fs-debug-banner" class="alert alert-info fade in" role="alert" style="margin-bottom:0 !important; font-size:lager;">' + 'FAOSTAT is in <strong>' + modeName + '</strong> mode. Using <strong>' + (this.CONFIG.datasource || 'DEFAULT') + '</strong> datasource' + '</div>');

        }

        try {
            if (!isLocal) this.initInterceptors();
        } catch (e) {
            log.error("FAOSTATAPIClient: Error initializing interceptors", e);
        }
    };

    FAOSTATAPIClient.prototype.initInterceptors = function () {
        var self = this;

        // Inject Authorization header in every AJAX request to /api/
        $(document).ajaxSend(function (event, jqXHR, settings) {
            // Check if it's an API call and not the token handshake itself
            if (settings.url.indexOf('/api/') !== -1 &&
                settings.url.indexOf('/guest/token') === -1 &&
                settings.url.indexOf('/ping') === -1 &&
                self.CONFIG.use_auth_header !== false) {
                var authHeader = self.getAuthHeader();
                if (authHeader) {
                    jqXHR.setRequestHeader('Authorization', authHeader);
                }
            }
        });

        // Global error handler for Authorization issues (401/403)
        $(document).ajaxError(function (event, jqXHR, ajaxSettings, thrownError) {
            if (ajaxSettings.url.indexOf('/api/') !== -1 && (jqXHR.status === 401 || jqXHR.status === 403)) {
                log.warn("Authorization error (401/403). Clearing tokens and re-handshaking.");
                amplify.store('guest_token', null);
                self.handshake();
            }
        });
    };

    FAOSTATAPIClient.prototype.getAuthHeader = function () {
        try {
            // 1. Check for Cognito Token (Logged Users)
            if (CognitoAuth && CognitoAuth.userManager && CognitoAuth.userManager.settings) {
                var settings = CognitoAuth.userManager.settings;
                var oidcKey = "oidc.user:" + settings.authority + ":" + settings.client_id;
                var oidcUser = localStorage.getItem(oidcKey) || sessionStorage.getItem(oidcKey);

                if (oidcUser) {
                    var user = JSON.parse(oidcUser);
                    if (user && user.access_token) {
                        return 'Bearer ' + user.access_token;
                    }
                }
            }
        } catch (e) {
            log.warn("Error retrieving Cognito token", e);
        }

        try {
            // 2. Check for Guest Token (Anonymous Users)
            if (typeof amplify !== 'undefined' && amplify.store) {
                var guestToken = amplify.store('guest_token');
                if (guestToken) {
                    return 'Bearer ' + guestToken;
                }
            } else {
                log.warn("Amplify not available for guest token");
            }
        } catch (e) {
            log.warn("Error retrieving guest token", e);
        }

        return null;
    };

    FAOSTATAPIClient.prototype.isValidToken = function (token) {
        if (!token) return false;
        try {
            var parts = token.split('.');
            if (parts.length !== 3) return false;
            var payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
            var now = Math.floor(Date.now() / 1000);
            // Expire 30 seconds before actual expiration to stay safe
            return payload.exp > (now + 30);
        } catch (e) {
            return false;
        }
    };

    FAOSTATAPIClient.prototype.handshake = function () {
        var self = this;

        if (this.IS_LOCAL) {
            log.info("Handshake: Local mode detected. Bypassing guest token handshake.");
            return Q.when("local-bypass");
        }

        if (typeof amplify === 'undefined' || !amplify.store) return Q.reject("amplify.store not found");

        if (this._handshaking) return this._handshaking;

        var guestToken = amplify.store('guest_token');

        // Verify if token exists AND is not expired/expiring soon
        if (guestToken && self.isValidToken(guestToken)) {
            return Q.when(guestToken);
        }

        log.info("Handshake: Fetching guest token from", self.CONFIG.guest_token_url);

        var ajaxOptions = {
            url: self.CONFIG.guest_token_url,
            type: 'GET',
            dataType: 'json'
        };

        this._handshaking = Q($.ajax(ajaxOptions)).then(function (resp) {
            if (resp && resp.token) {
                amplify.store('guest_token', resp.token, 300000);
                return resp.token;
            }
            log.error("Handshake FAILED: No token in response.");
            return Q.reject("No token in response");
        }).fail(function (err) {
            log.error("Handshake ERROR for URL:", self.CONFIG.guest_token_url, err);
            return Q.reject(err);
        }).finally(function () {
            delete self._handshaking;
        });

        return this._handshaking;
    };

    FAOSTATAPIClient.prototype.config = function (c) {

        /* Extend default configuration. */
        var configToApply = c || {};

        this.CONFIG = $.extend(true, {}, this.CONFIG, configToApply);

        // EXTRA PROTECTION: If we are in DEV mode, we MUST use appropriate APIs.
        // Prevent external config (from build/application.js) to revert us to production.
        if (this.IS_LOCAL) {
            this.CONFIG.base_url = 'https://faostatservices-internal.fao.org/api/v1/';
            this.CONFIG.guest_token_url = 'https://faostatservices-internal.fao.org/api/v1/auth/guest';
            this.CONFIG.datasource = "INTERNAL";
            console.log("FAOSTATAPIClient.config: LOCAL mode enforced. base_url:", this.CONFIG.base_url);
        } else if (this.IS_DEV) {
            this.CONFIG.base_url = 'https://api-faostat.dev.fao.org/api/v1/';
            this.CONFIG.guest_token_url = 'https://api-faostat.dev.fao.org/api/v1/auth/guest';
            console.log("FAOSTATAPIClient.config: CLOUD DEV mode enforced. base_url:", this.CONFIG.base_url);
        }

        // Update debug banner with version if it exists
        if (this.IS_DEV && this.CONFIG.DATE_UPDATE && this.CONFIG.DATE_UPDATE.indexOf('@@') === -1) {
            var $banner = $('#fs-debug-banner');
            if ($banner.length > 0 && $banner.text().indexOf('Version') === -1) {
                $banner.append(' | Version: <strong>' + this.CONFIG.DATE_UPDATE + '</strong>');
            }
        }
    };

    FAOSTATAPIClient.prototype.rankings = function (c) {

        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_rankings_defaults(config);
        if (this.is_valid_rankings(config)) {
            var url = this.CONFIG.base_url + config.lang + '/rankings/',
                url_data = ['base_url', 'lang'],
                compressArray = false,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "datasource": config.datasource,
                "output_type": config.output_type,
                "domain_codes": config.domain_codes,
                "List1Codes": config.List1Codes,
                "List2Codes": config.List2Codes,
                "List3Codes": config.List3Codes,
                "List4Codes": config.List4Codes,
                "List5Codes": config.List5Codes,
                "List6Codes": config.List6Codes,
                "List7Codes": config.List7Codes,
                //"List8Codes": config.List8Codes,
                //"List9Codes": config.List9Codes,
                "filter_list": config.filter_list,
                "rank_type": config.rank_type,
                "limit": config.limit
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }

            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.rankings; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            //console.log('data is ', data);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'POST'
                })).then(function (d) {
                    console.log("API.rankings RESPONSE:", d);
                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_rankings = function (config) {
        var parameters = ["output_type", "lang", "domain_codes", "List1Codes", "List2Codes", "List3Codes", "List4Codes", "List5Codes", "List6Codes", "List7Codes", /*"List8Codes", "List9Codes",*/ "filter_list", "rank_type", "limit"],
            i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_rankings", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_rankings_defaults = function (config) {
        var i,
            parameters = ["datasource", "output_type", "lang", "domain_codes", "List1Codes", "List2Codes", "List3Codes", "List4Codes", "List5Codes", "List6Codes", "List7Codes", /*"List8Codes", "List9Codes",*/ "filter_list", "rank_type", "limit"],
            defaults = {
                "output_type": "objects", "lang": "en", "rank_type": "ASC", "limit": "5"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_rankings", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.reportheaders = function (c) {
        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_reportheaders_defaults(config);
        if (this.is_valid_reportheaders(config)) {
            var url = this.CONFIG.base_url + config.lang + '/report/headers/',
                url_data = ['base_url', 'lang'],
                compressArray = false,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "output_type": config.output_type,
                "domain_code": config.domain_code,
                "report_code": config.report_code,
                "List1Codes": config.List1Codes,
                "List2Codes": config.List2Codes,
                "List3Codes": config.List3Codes,
                "List4Codes": config.List4Codes,
                "List5Codes": config.List5Codes,
                "List6Codes": config.List6Codes,
                "List7Codes": config.List7Codes,
                //"List8Codes": config.List8Codes,
                //"List9Codes": config.List9Codes,
                "List1AltCodes": config.List1AltCodes,
                "List2AltCodes": config.List2AltCodes,
                "List3AltCodes": config.List3AltCodes,
                "List4AltCodes": config.List4AltCodes,
                "List5AltCodes": config.List5AltCodes,
                "List6AltCodes": config.List6AltCodes,
                "List7AltCodes": config.List7AltCodes,
                //"List8AltCodes": config.List8AltCodes,
                //"List9AltCodes": config.List9AltCodes,
                "datasource": config.datasource
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }

            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.reportheaders; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'POST'
                })).then(function (d) {
                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_reportheaders = function (config) {
        var parameters = ["output_type", "domain_code", "report_code", "List1Codes", "List2Codes", "List3Codes", "List4Codes", "List5Codes", "List6Codes", "List7Codes", "List1AltCodes", "List2AltCodes", "List3AltCodes", "List4AltCodes", "List5AltCodes", "List6AltCodes", "List7AltCodes"],
            i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_reportheaders", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_reportheaders_defaults = function (config) {
        var i,
            parameters = ["output_type", "domain_code", "report_code", "List1Codes", "List2Codes", "List3Codes", "List4Codes", "List5Codes", "List6Codes", "List7Codes", "List1AltCodes", "List2AltCodes", "List3AltCodes", "List4AltCodes", "List5AltCodes", "List6AltCodes", "List7AltCodes"],
            defaults = {
                "output_type": "objects"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_reportheaders", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.reportdata = function (c) {
        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_reportdata_defaults(config);
        if (this.is_valid_reportdata(config)) {
            var url = this.CONFIG.base_url + config.lang + '/report/data/',
                url_data = ['base_url', 'lang'],
                compressArray = false,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "datasource": config.datasource,
                "output_type": config.output_type,
                "domain_code": config.domain_code,
                "report_code": config.report_code,
                "List1Codes": config.List1Codes,
                "List2Codes": config.List2Codes,
                "List3Codes": config.List3Codes,
                "List4Codes": config.List4Codes,
                "List5Codes": config.List5Codes,
                "List6Codes": config.List6Codes,
                "List7Codes": config.List7Codes,
                "List8Codes": config.List8Codes,
                "List9Codes": config.List9Codes,
                "List1AltCodes": config.List1AltCodes,
                "List2AltCodes": config.List2AltCodes,
                "List3AltCodes": config.List3AltCodes,
                "List4AltCodes": config.List4AltCodes,
                "List5AltCodes": config.List5AltCodes,
                "List6AltCodes": config.List6AltCodes,
                "List7AltCodes": config.List7AltCodes,
                "List8AltCodes": config.List8AltCodes,
                "List9AltCodes": config.List9AltCodes
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }

            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.reportdata; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'POST'
                })).then(function (d) {
                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_reportdata = function (config) {
        var parameters = ["output_type", "lang", "domain_code", "report_code", "List1Codes", "List2Codes", "List3Codes", "List4Codes", "List5Codes", "List6Codes", "List7Codes", "List1AltCodes", "List2AltCodes", "List3AltCodes", "List4AltCodes", "List5AltCodes", "List6AltCodes", "List7AltCodes"],
            i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_reportdata", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_reportdata_defaults = function (config) {
        var i,
            parameters = ["output_type", "lang", "domain_code", "report_code", "List1Codes", "List2Codes", "List3Codes", "List4Codes", "List5Codes", "List6Codes", "List7Codes", "List1AltCodes", "List2AltCodes", "List3AltCodes", "List4AltCodes", "List5AltCodes", "List6AltCodes", "List7AltCodes"],
            defaults = {
                "output_type": "objects", "lang": "en"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_reportdata", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.datasize = function (c) {
        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_datasize_defaults(config);
        if (this.is_valid_datasize(config)) {
            var url = this.CONFIG.base_url + config.lang + '/datasize/',
                url_data = ['base_url', 'lang'],
                compressArray = false,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "output_type": config.output_type,
                "domain_codes": config.domain_codes,
                "List1Codes": config.List1Codes,
                "List2Codes": config.List2Codes,
                "List3Codes": config.List3Codes,
                "List4Codes": config.List4Codes,
                "List5Codes": config.List5Codes,
                "List6Codes": config.List6Codes,
                "List7Codes": config.List7Codes,
                "List8Codes": config.List8Codes,
                "List9Codes": config.List9Codes,
                "no_records": config.no_records,
                "null_values": config.null_values
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }

            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.datasize; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'POST'
                })).then(function (d) {
                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_datasize = function (config) {
        var parameters = ["output_type", "lang", "domain_codes", "List1Codes", "List2Codes", "List3Codes", "List4Codes", "List5Codes", "List6Codes", "List7Codes", "List8Codes", "List9Codes", "no_records", "null_values"],
            i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_datasize", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_datasize_defaults = function (config) {
        var i,
            parameters = ["output_type", "lang", "domain_codes", "List1Codes", "List2Codes", "List3Codes", "List4Codes", "List5Codes", "List6Codes", "List7Codes", "List8Codes", "List9Codes", "no_records", "null_values"],
            defaults = {
                "output_type": "objects", "lang": "en", "no_records": "1", "null_values": "false"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_datasize", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.groupsanddomains = function (c) {
        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_groupsanddomains_defaults(config);
        if (this.is_valid_groupsanddomains(config)) {
            var url = this.CONFIG.base_url + config.lang + '/groupsanddomains',
                url_data = ['base_url', 'lang'],
                compressArray = false,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "datasource": config.datasource, "section": config.section
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }


            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.groupsanddomains; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'GET'
                })).then(function (d) {
                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_groupsanddomains = function (config) {
        var parameters = ['lang'], i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_groupsanddomains", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_groupsanddomains_defaults = function (config) {
        var i,
            parameters = ["datasource", "lang", "section"],
            defaults = {
                "lang": "en"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_groupsanddomains", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.dimensions = function (c) {
        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_dimensions_defaults(config);
        if (this.is_valid_dimensions(config)) {
            var url = this.CONFIG.base_url + config.lang + '/dimensions/' + config.domain_code + '/',
                url_data = ['base_url', 'lang', 'domain_code'],
                compressArray = false,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "datasource": config.datasource, "report_code": config.report_code, "full": config.full
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }

            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.dimensions; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'GET'
                })).then(function (d) {
                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_dimensions = function (config) {
        var parameters = ['lang', 'domain_code'], i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_dimensions", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_dimensions_defaults = function (config) {
        var i,
            parameters = ["datasource", "report_code", "lang", "domain_code", "full"],
            defaults = {
                "lang": "en", "full": "false"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_dimensions", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.codes = function (c) {
        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_codes_defaults(config);
        if (this.is_valid_codes(config)) {
            var url = this.CONFIG.base_url + config.lang + '/codes/' + config.id + '/' + config.domain_code + '/',
                url_data = ['base_url', 'lang', 'id', 'domain_code'],
                compressArray = false,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "datasource": config.datasource,
                "report_code": config.report_code,
                "whitelist": config.whitelist,
                "blacklist": config.blacklist,
                "show_lists": config.show_lists
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }

            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.codes; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'GET'
                })).then(function (d) {
                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_codes = function (config) {
        var parameters = ['lang', 'id', 'domain_code'], i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_codes", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_codes_defaults = function (config) {
        var i,
            parameters = ["datasource", "domain_code", "report_code", "lang", "id", "whitelist", "blacklist", "show_lists"],
            defaults = {
                "lang": "en", "whitelist": "[]", "blacklist": "[]", "show_lists": "true"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_codes", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.groups = function (c) {
        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_groups_defaults(config);
        if (this.is_valid_groups(config)) {
            var url = this.CONFIG.base_url + config.lang + '/groups/',
                url_data = ['base_url', 'lang'],
                compressArray = false,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "datasource": config.datasource, "whitelist": config.whitelist, "blacklist": config.blacklist
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }

            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.groups; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'GET'
                })).then(function (d) {
                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_groups = function (config) {
        var parameters = ['lang'], i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_groups", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_groups_defaults = function (config) {
        var i,
            parameters = ["datasource", "whitelist", "blacklist", "lang"],
            defaults = {
                "whitelist": "[]", "blacklist": "[]", "lang": "en"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_groups", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.domains = function (c) {
        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_domains_defaults(config);
        if (this.is_valid_domains(config)) {
            var url = this.CONFIG.base_url + config.lang + '/domains/' + config.group_code + '/',
                url_data = ['base_url', 'lang', 'group_code'],
                compressArray = false,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "datasource": config.datasource, "whitelist": config.whitelist, "blacklist": config.blacklist
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }

            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.domains; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'GET'
                })).then(function (d) {
                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_domains = function (config) {
        var parameters = ['lang', 'group_code'], i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_domains", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_domains_defaults = function (config) {
        var i,
            parameters = ["datasource", "lang", "group_code", "whitelist", "blacklist"],
            defaults = {
                "lang": "en", "whitelist": "[]", "blacklist": "[]"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_domains", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.bulkdownloads = function (c) {
        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_bulkdownloads_defaults(config);
        if (this.is_valid_bulkdownloads(config)) {
            var url = this.CONFIG.base_url + config.lang + '/bulkdownloads/' + config.domain_code + '/',
                url_data = ['base_url', 'lang', 'domain_code'],
                compressArray = false,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "datasource": config.datasource
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }

            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.bulkdownloads; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'GET'
                })).then(function (d) {
                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_bulkdownloads = function (config) {
        var parameters = ['lang', 'domain_code'], i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_bulkdownloads", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_bulkdownloads_defaults = function (config) {
        var i,
            parameters = ["datasource", "lang", "domain_code"],
            defaults = {
                "lang": "en"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_bulkdownloads", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.updates = function (c) {
        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_updates_defaults(config);
        if (this.is_valid_updates(config)) {
            var url = this.CONFIG.base_url + config.lang + '/updates/' + config.domain_code + '/',
                url_data = ['base_url', 'lang', 'domain_code'],
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "datasource": config.datasource,
                "output_type": "csv"
            });

            for (var i = 0; i < url_data.length; i++) delete data[url_data[i]];

            if (this.CONFIG.log) log.info("API.updates; request", data);

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            return Q.when({ url: url, data: data });

            /*

            if (v === undefined) {                
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'GET'
                })).then(function (d) {
                    console.log('invincible')
                    // TODO: this should be at the schema level for each request and not a global one                    
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                console.log('stuff')
                return Q.when(v);
            }
            */

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_updates = function (config) {
        var parameters = ['lang', 'domain_code'], i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_updates", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_updates_defaults = function (config) {
        var i,
            parameters = ["datasource", "lang", "domain_code"],
            defaults = {
                "lang": "en"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_updates_defaults", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.documents = function (c) {
        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_documents_defaults(config);
        if (this.is_valid_documents(config)) {
            var url = this.CONFIG.base_url + config.lang + '/documents/' + config.domain_code + '/',
                url_data = ['base_url', 'lang', 'domain_code'],
                compressArray = false,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "datasource": config.datasource
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }

            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.documents; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'GET'
                })).then(function (d) {
                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_documents = function (config) {
        var parameters = ['lang', 'domain_code'], i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_documents", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_documents_defaults = function (config) {
        var i,
            parameters = ["datasource", "lang", "domain_code"],
            defaults = {
                "lang": "en"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_documents", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.suggestions = function (c) {
        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_suggestions_defaults(config);
        if (this.is_valid_suggestions(config)) {
            var url = this.CONFIG.base_url + config.lang + '/suggestions',
                url_data = ['base_url', 'lang'],
                compressArray = false,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "datasource": config.datasource, "q": config.q
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }

            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.suggestions; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'GET'
                })).then(function (d) {
                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_suggestions = function (config) {
        var parameters = ['lang', 'q'], i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_suggestions", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_suggestions_defaults = function (config) {
        var i,
            parameters = ["datasource", "lang", "q"],
            defaults = {
                "lang": "en"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_suggestions", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.search = function (c) {
        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_search_defaults(config);
        if (this.is_valid_search(config)) {
            var url = this.CONFIG.base_url + config.lang + '/search',
                url_data = ['base_url', 'lang'],
                compressArray = false,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "datasource": config.datasource, "q": config.q
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }

            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.search; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'GET'
                })).then(function (d) {
                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_search = function (config) {
        var parameters = ['lang', 'q'], i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_search", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_search_defaults = function (config) {
        var i,
            parameters = ["datasource", "lang", "q"],
            defaults = {
                "lang": "en"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_search", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.metadata = function (c, printable) {
        var config = $.extend(true, {}, this.CONFIG, c || {}),
            is_print = (printable) ? '_print' : '';

        config = this.apply_metadata_defaults(config);
        if (this.is_valid_metadata(config)) {
            var url = this.CONFIG.base_url + config.lang + '/metadata' + is_print + '/' + config.domain_code + '',
                url_data = ['base_url', 'lang', 'domain_code'],
                compressArray = false,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "datasource": config.datasource
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }

            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.metadata; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'GET'
                })).then(function (d) {
                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_metadata = function (config) {
        var parameters = ['lang', 'domain_code'], i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_metadata", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_metadata_defaults = function (config) {
        var i,
            parameters = ["datasource", "lang"],
            defaults = {
                "lang": "en"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_metadata", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.definitions_types = function (c) {
        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_definitions_types_defaults(config);
        if (this.is_valid_definitions_types(config)) {
            var url = this.CONFIG.base_url + config.lang + '/definitions/types',
                url_data = ['base_url', 'lang'],
                compressArray = false,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "datasource": config.datasource
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }

            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.definitions_types; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'GET'
                })).then(function (d) {
                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_definitions_types = function (config) {
        var parameters = ['lang'], i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_definitions_types", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_definitions_types_defaults = function (config) {
        var i,
            parameters = ["datasource", "lang"],
            defaults = {
                "lang": "en"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_definitions_types", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.definitions_by_type = function (c) {
        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_definitions_by_type_defaults(config);
        if (this.is_valid_definitions_by_type(config)) {
            var url = this.CONFIG.base_url + config.lang + '/definitions/types/' + config.type + '',
                url_data = ['base_url', 'lang', 'type'],
                compressArray = false,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "datasource": config.datasource
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }

            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.definitions_by_type; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'GET'
                })).then(function (d) {
                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_definitions_by_type = function (config) {
        var parameters = ['lang', 'type'], i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_definitions_by_type", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_definitions_by_type_defaults = function (config) {
        var i,
            parameters = ["datasource", "lang", "type"],
            defaults = {
                "lang": "en"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_definitions_by_type", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.definitions_domain = function (c) {
        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_definitions_domain_defaults(config);
        if (this.is_valid_definitions_domain(config)) {
            var url = this.CONFIG.base_url + config.lang + '/definitions/domain/' + config.domain_code + '',
                url_data = ['base_url', 'lang', 'domain_code'],
                compressArray = false,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "datasource": config.datasource
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }

            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.definitions_domain; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'GET'
                })).then(function (d) {
                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_definitions_domain = function (config) {
        var parameters = ['lang', 'domain_code'], i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_definitions_domain", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_definitions_domain_defaults = function (config) {
        var i,
            parameters = ["datasource", "lang", "domain_code"],
            defaults = {
                "lang": "en"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_definitions_domain", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.definitions_domain_by_type = function (c) {
        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_definitions_domain_by_type_defaults(config);
        if (this.is_valid_definitions_domain_by_type(config)) {
            var url = this.CONFIG.base_url + config.lang + '/definitions/domain/' + config.domain_code + '/' + config.type + '',
                url_data = ['base_url', 'lang', 'domain_code', 'type'],
                compressArray = false,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "datasource": config.datasource, "output_type": config.output_type
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }

            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.definitions_domain_by_type; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'GET'
                })).then(function (d) {
                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }
                    return d;
                });
            } else {
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.is_valid_definitions_domain_by_type = function (config) {
        var parameters = ['lang', 'domain_code', 'type'], i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_definitions_domain_by_type", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_definitions_domain_by_type_defaults = function (config) {
        var i,
            parameters = ["datasource", "output_type", "lang", "domain_code", "type"],
            defaults = {
                "output_type": "objects", "lang": "en"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_definitions_domain_by_type", defaults, parameters, config);
        }

        return config;
    };

    FAOSTATAPIClient.prototype.data = function (c) {
        var config = $.extend(true, {}, this.CONFIG, c || {});
        config = this.apply_data_defaults(config);

        if (this.is_valid_data(config)) {
            var url = this.CONFIG.base_url + config.lang + '/data/' + config.domain_code + '',
                url_data = ['base_url', 'lang', 'domain_code'],
                compressArray = true,
                traditional = true,
                self = this;

            // if advanced
            var data = $.extend(true, {}, c, {
                "datasource": config.datasource, "output_type": config.output_type, "caching": 'false'
            });

            for (var i = 0; i < url_data.length; i++) {
                delete data[url_data[i]];
            }

            // parse arrays to strings
            // this will reduce the length of the URL
            if (compressArray === true) {
                $.each(data, function (k, v) {
                    if (Array.isArray(v)) {
                        data[k] = v.join(",");
                    }
                });
            }

            if (this.CONFIG.log) {
                log.info("API.data; request", data);
            }

            var key = JSON.stringify($.extend({ url: url }, data));
            var v = this.store(key);

            if (v === undefined) {
                return Q($.ajax({
                    url: url,
                    // TODO: this should be an option in the schema
                    traditional: traditional,
                    data: data,
                    type: 'GET'
                })).then(function (d) {

                    // Remove blacklisted items 
                    // DEPRECATED, use the array option below
                    /*                   
                    if (config.blacklist) {               
                        var toRemove = [];
                        $.each(d.data, function (k,v) {
                            var item = Object.keys(config.blacklist)[0];
                            var exclude = config.blacklist[item];         
                            if (v[item] == exclude) toRemove.push(k);
                        })
                        var i = toRemove.length;
                        while (i--) d.data.splice(toRemove[i],1);
                    }
                    */
                    if (config.blacklistArray) {
                        // ***** This seems to not work
                        // var toRemove = [];
                        $.each(config.blacklistArray, function (i, x) {
                            $.each(d.metadata.dsd, function (k, v) {
                                var obj = Object.keys(x)[0];
                                if ((obj == v.dimension_id) && (v.type != "label")) $.each(x[obj], function (j, y) {
                                    $.each(d.data, function (index, value) {
                                        var exclude = Object.values(value)[k];
                                        if (exclude == y) {
                                            // ***** This seems to not work
                                            // toRemove.push(index);
                                            d.data[index]['Value'] = 'REMOVEREMOVEREMOVE';
                                        }
                                    })
                                });
                            })
                        })
                        /*
                        // ***** This seems to not work
                        var h = toRemove.length;
                        while (h--) d.data.splice(toRemove[h],1);
                        */
                    }

                    if (d && d.metadata && d.metadata.processing_time) self.show_execution_time(d.metadata.processing_time);

                    // TODO: this should be at the schema level for each request and not a global one
                    try {
                        self.store(key, d);
                    } catch (e) {
                        // catching for quota exceed
                    }



                    if (d.data != undefined) d.data = d.data.filter(function (value) { return (value['Value'] != "REMOVEREMOVEREMOVE") })

                    return d;
                });
            } else {
                self.show_execution_time('-');
                return Q.when(v);
            }

        }
        throw 400;
    };

    FAOSTATAPIClient.prototype.show_execution_time = function (time) {
        var out = parseInt(time);
        if (isNaN(out)) out = "--";
        $('[data-role="fs_exectution_time_api"]').html(out + "ms");
        $('[data-role="fs_exectution_time_api_title"]').attr('title', out + "ms");
    }

    FAOSTATAPIClient.prototype.is_valid_data = function (config) {
        var parameters = ['lang', 'domain_code'], i;
        for (i = 0; i < parameters.length; i += 1) {
            if (config[parameters[i]] === undefined) {
                log.error('Parameter "' + parameters[i] + '" is undefined. Please check your request.');
                throw 'Parameter "' + parameters[i] + '" is undefined. Please check your request.';
            }
        }
        if (this.CONFIG.log) {
            log.info("API.prototype.is_valid_data", true);
        }
        return true;
    };

    FAOSTATAPIClient.prototype.apply_data_defaults = function (config) {
        var i,
            parameters = ["datasource", "output_type", "lang"],
            defaults = {
                "output_type": "objects", "lang": "en"
            },
            key;
        for (i = 0; i < Object.keys(defaults).length; i += 1) {
            if (defaults[Object.keys(defaults)[i]] === '[]') {
                defaults[Object.keys(defaults)[i]] = [];
            }
        }
        for (i = 0; i < parameters.length; i += 1) {
            key = parameters[i];
            try {
                config[key] = config[key] !== undefined ? config[key] : defaults[key];
            } catch (ignore) {
                // No default value available for this parameter.
            }
        }

        if (this.CONFIG.log) {
            log.info("API.prototype.apply_data", defaults, parameters, config);
        }

        return config;
    };


    /* used to get a key/value */
    FAOSTATAPIClient.prototype.store = function (key, value) {

        /* if mode = 'dev' */
        if (this.CONFIG.hasOwnProperty('mode') && this.CONFIG.mode === 'dev') {
            return undefined;
        }

        var expireStoreTime = 300000;
        // 300000 (5 minutes)
        // 600000 (10 minutes)
        // 1200000 (20 minutes)
        // 1800000 (30 minutes)
        // 3600000 (60 minutes)

        if (value !== undefined) {
            if (this.CONFIG.log) {
                log.info("Stored", key);
            }
            return amplify.store(key, value, expireStoreTime);
        } else {
            if (this.CONFIG.log) {
                log.info("Get Stored", key);
            }
            return amplify.store(key);
        }

    };

    // Auto-wrap API methods to ensure handshake is valid before every request
    ["rankings", "reportheaders", "reportdata", "datasize", "groupsanddomains", "dimensions", "codes", "groups", "domains", "bulkdownloads", "updates", "documents", "suggestions", "search", "metadata", "definitions_types", "definitions_by_type", "definitions_domain", "definitions_domain_by_type", "data"].forEach(function (m) {
        var o = FAOSTATAPIClient.prototype[m];
        if (typeof o === 'function') {
            FAOSTATAPIClient.prototype[m] = function () {
                var self = this, args = arguments;
                return self.handshake().then(function () { return o.apply(self, args); });
            };
        }
    });

    return new FAOSTATAPIClient;

});