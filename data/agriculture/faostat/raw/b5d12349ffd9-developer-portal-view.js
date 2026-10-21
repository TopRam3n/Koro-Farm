define([
    'jquery',
    'underscore',
    'backbone',
    'views/base/view',
    'handlebars',
    'text!templates/developer-portal.hbs',
    'globals/CognitoAuth',
    'faostatapiclient',
    'i18n!nls/home',
    'lib/compare/compare-filter',
    'config/compare/Config',
    'i18n!nls/compare',
    'q',
    'config/Events',
    'config/GABindings',
    'amplify'
], function ($, _, Backbone, View, Handlebars, template, CognitoAuth, FAOSTATAPIClient, i18nLabels, Filter, CM, i18nCompareLabels, Q, E, A) {

    'use strict';

    var DeveloperPortalView = View.extend({

        autoRender: true,

        className: 'developer-portal',

        template: Handlebars.compile(template),

        events: {
            'click #btn-copy-token': 'copyTokenToClipboard',
            'click #btn-login-cognito': 'loginCognito',
            'click #btn-generate-query': 'generateApiQuery',
            'click #btn-reset-query': 'resetQueryBuilder',
            'click #btn-copy-qb-query': 'copyGeneratedQuery',
            'click #btn-copy-excel-snippet': 'copyExcelSnippet'
        },

        initialize: function () {
            console.log("DeveloperPortalView: initialize");
            View.prototype.initialize.apply(this, arguments);
            // FAOSTATAPIClient is already an instance
            this.api = FAOSTATAPIClient;

            // Query Builder state
            this.qb = {
                groups: {},
                domains: {},
                filters: {},
                dimensionMapping: {},
                domainCode: null
            };
        },

        attach: function () {
            View.prototype.attach.call(this, arguments);
            this.updateAuthStatus();
            this.checkSystemStatus();
            this.initQueryBuilder();
        },

        updateAuthStatus: function () {
            var self = this;
            var $loading = this.$el.find('#auth-status-loading');
            var $content = this.$el.find('#auth-status-content');
            var $error = this.$el.find('#auth-status-error');

            CognitoAuth.userManager.getUser().then(function (user) {
                $loading.hide();
                $content.show();
                $error.hide();

                var $loggedInSection = self.$el.find('#auth-content-logged-in');
                var $guestSection = self.$el.find('#auth-content-guest');

                if (user && !user.expired) {
                    $loggedInSection.show();
                    $guestSection.hide();
                    self.$el.find('#user-email').text(user.profile.email);
                    self.$el.find('#access-token').text(user.access_token);
                    self.currentToken = user.access_token;
                    self.updateExcelSnippet();
                } else {
                    $loggedInSection.hide();
                    $guestSection.show();

                    // Verify if a guest token exists just in case, but we don't show it
                    var guestToken = typeof amplify !== 'undefined' ? amplify.store('guest_token') : null;
                    if (!guestToken) {
                        // If no token at all, show error after a small delay to allow handshake
                        setTimeout(function () {
                            if (!amplify.store('guest_token')) {
                                $content.hide();
                                $error.show();
                            }
                        }, 2000);
                    }
                }

            }).catch(function (error) {
                console.error("Error getting user:", error);
                $loading.hide();
                $content.hide();
                $error.show();
            });
        },

        copyTokenToClipboard: function () {
            var token = this.$el.find('#access-token').text();
            var $msg = this.$el.find('#copy-success-msg');

            var textArea = document.createElement("textarea");
            textArea.value = token;
            document.body.appendChild(textArea);
            textArea.select();

            try {
                document.execCommand('copy');
                $msg.fadeIn().delay(2000).fadeOut();
                amplify.publish(E.GA4_EVENT, $.extend(true, {}, A.developer_portal.copy_token, {}));
            } catch (err) {
                console.error('Fallback: Oops, unable to copy', err);
            }

            document.body.removeChild(textArea);
        },

        loginCognito: function () {
            CognitoAuth.userManager.signinRedirect();
        },

        getTemplateData: function () {
            var siteUrl = window.location.href.split('#')[0].split('?')[0];
            // If the URL ends with a file (e.g. index.html), strip it to get the directory
            if (siteUrl.match(/\/.*\..*$/)) {
                siteUrl = siteUrl.substring(0, siteUrl.lastIndexOf('/') + 1);
            }
            // Ensure it ends with a slash
            if (siteUrl.length > 0 && siteUrl.charAt(siteUrl.length - 1) !== '/') {
                siteUrl += '/';
            }

            return $.extend(true,
                {
                    baseUrl: this.api.CONFIG.base_url,
                    siteUrl: siteUrl
                },
                i18nLabels
            );
        },

        checkSystemStatus: function () {
            var self = this;
            var baseUrl = this.api.CONFIG.base_url;
            var pingUrl = baseUrl + "ping";

            // Update the display to show the endpoint we are checking
            this.$el.find('#api-system-endpoint').text(pingUrl);

            var $badge = this.$el.find('#api-status-badge');

            $.ajax({
                url: pingUrl,
                type: 'GET',
                timeout: 5000 // 5 seconds timeout
            }).done(function () {
                $badge.css({
                    'background-color': '#5cb85c',
                    'color': 'white'
                }).text('Online');
            }).fail(function (jqXHR, textStatus) {
                var msg = 'Offline';
                if (textStatus === 'timeout') {
                    msg = 'Timeout';
                }
                $badge.css({
                    'background-color': '#d9534f',
                    'color': 'white'
                }).text(msg);
                console.error("API Ping failed:", textStatus);
            });
        },

        /* --- Query Builder Methods --- */

        initQueryBuilder: function () {
            var self = this;
            this.$QB_GROUPS = this.$el.find('[data-role="qb-groups"]');
            this.$QB_DOMAINS = this.$el.find('[data-role="qb-domains"]');
            this.$QB_FILTERS = this.$el.find('[data-role="qb-filters"]');

            amplify.publish(E.LOADING_SHOW, {container: this.$QB_GROUPS});

            this.api.groups({}).then(function(json) {
                self.createGroupFilter(json);
            }).fail(function(e) {
                console.error("QueryBuilder.initQueryBuilder error", e);
                amplify.publish(E.LOADING_HIDE, { container: self.$QB_GROUPS});
            });
        },

        blacklistClientside: function (json, blacklist) {
            var toRemove = [];            
            $.each(json.data, function (k, v){                
                $.each(blacklist, function (bk, bv){                    
                    if (bv == v.code) toRemove.push(k);                                           
                });                
            });
            var i = toRemove.length;
            while (i--) json.data.splice(toRemove[i],1);
            return json;
        },

        createGroupFilter: function(json) {                        
            var self = this,
                groupsData = json.data,
                filter = new Filter({
                    container: this.$QB_GROUPS,
                    title: i18nCompareLabels.groups,
                    addEmptySelection: true,
                    placeholder: " ",
                    data: groupsData
                });

            this.qb.groups = { filter: filter, json: json };
            this.qb.groups.$DD = filter.getDropDown();

            this.qb.groups.$DD.change(function(e) {
                self.onGroupChange(e.val, e.added.text);
            });
        },

        onGroupChange: function(code, label) {
            var self = this;
            this.$QB_DOMAINS.empty();
            this.$QB_FILTERS.empty();
            this.$el.find('#qb-result-container').hide();
            this.updateExcelSnippet();

            amplify.publish(E.LOADING_SHOW, { container: this.$QB_DOMAINS});

            this.api.domains({
                group_code: code
            }).then(function(json) {
                self.createDomainFilter(json);
            });
        },

        createDomainFilter: function(json) {            
            var self = this;

            var filter = new Filter({
                container: this.$QB_DOMAINS,
                title: i18nCompareLabels.domains,
                placeholder: " ",
                data: json.data
            });

            this.qb.domains = { filter: filter, json: json };
            this.qb.domains.$DD = filter.getDropDown();

            this.qb.domains.$DD.change(function(e) {
                self.onDomainChange(e.val, e.added.text);
            });
        },

        onDomainChange: function(code, label) {
            this.qb.domainCode = code;
            this.$el.find('#qb-result-container').hide();
            this.updateExcelSnippet();
            this.createFiltersByDomain();
        },

        createFiltersByDomain: function() {
            var self = this;
            this.$QB_FILTERS.empty();
            this.qb.filters = {};

            amplify.publish(E.LOADING_SHOW, { container: this.$QB_FILTERS});

            this.api.dimensions({
                domain_code: this.qb.domainCode,
                full: true
            }).then(_.bind(this._preloadDomainDimensions, this))
              .then(_.bind(function(json) {
                  amplify.publish(E.LOADING_HIDE, { container: self.$QB_FILTERS});
                  var indexRequest = 0;

                  _.each(self.qb.dimensionMapping, _.bind(function(parameter, id) {
                      try {
                          var v = json[indexRequest];
                          v.container = self.createFilterContainer(self.$QB_FILTERS, id);
                          v.title = i18nCompareLabels[id.toLowerCase()] || id;
                          v.parameter = id; // use id directly
                          v.id = id;

                          v.ddOptions = {
                              multiple: true,
                              addEmptySelection: true,
                              allowClear: false,
                              show: true
                          };
                          v.placeholder = " ";

                          self.qb.filters[id] = { filter: new Filter(v) };
                          indexRequest += 1;                            
                      } catch(e) {
                          console.error("Filter creation error:", e);
                      }
                  }, self));

            }, this));
        },

        _preloadDomainDimensions: function (json) {
            var r = [],
                domainCode = this.qb.domainCode,
                self = this;

            this.qb.dimensionMapping = {};

            _.each(json.data, _.bind(function (c) {
                var id = c.id;
                this.qb.dimensionMapping[id] = c.parameter;

                r.push(
                    this.api.codes({
                        id: id,
                        domain_code: domainCode,
                        show_lists: true,
                    })
                );
            }, this));

            return Q.all(r);
        },

        createFilterContainer: function ($CONTAINER, id) {
            var html = '<div style="flex: 1; min-width: 230px; margin-bottom: 10px;" data-role="filter-' + id + '"></div>';
            $CONTAINER.append(html);
            return $CONTAINER.find('[data-role="filter-' + id + '"]');
        },

        resetQueryBuilder: function() {
            if (this.qb.groups && this.qb.groups.$DD) {
                this.qb.groups.$DD.select2("val", "");
            }
            this.$QB_DOMAINS.empty();
            this.$QB_FILTERS.empty();
            this.$el.find('#qb-result-container').hide();
            this.$el.find('#qb-generated-query').val('');
            this.qb.domainCode = null;
            this.updateExcelSnippet();
        },

        generateApiQuery: function() {
            var self = this;

            if (!this.qb.groups.$DD || this.qb.groups.$DD.val() === '') {
                amplify.publish(E.NOTIFICATION_WARNING, { title: 'Warning', text: 'Please select a Group' });
                return;
            }
            if (!this.qb.domains.$DD || this.qb.domains.$DD.val() === '') {
                amplify.publish(E.NOTIFICATION_WARNING, { title: 'Warning', text: 'Please select a Domain' });
                return;
            }

            var apiBase = this.api.CONFIG.base_url + "en/data/" + this.qb.domainCode;
            var params = [];

            try {
                _.each(Object.keys(this.qb.filters), function (filterKey) {
                    var filterObj = self.qb.filters[filterKey].filter;
                    // Check if it's visible or hidden, get selected codes
                    var fData = filterObj.getFilter();
                    if (fData.codes && fData.codes.length > 0) {
                        params.push(fData.parameter + "=" + encodeURIComponent(fData.codes.join(',')));
                    }
                });
                
                var queryUrl = apiBase;
                if (params.length > 0) {
                    queryUrl += "?" + params.join("&");
                }

                this.$el.find('#qb-generated-query').val(queryUrl);
                this.$el.find('#qb-result-container').fadeIn();
                this.updateExcelSnippet();

                amplify.publish(E.GA4_EVENT, $.extend(true, {}, A.developer_portal.generate_query, {
                    label: queryUrl
                }));

            } catch (e) {
                console.error("Query generation error:", e);
            }
        },

        copyGeneratedQuery: function() {
            var $input = this.$el.find('#qb-generated-query');
            $input.select();
            
            try {
                document.execCommand('copy');
                amplify.publish(E.NOTIFICATION_SUCCESS, { text: 'Query copied to clipboard!' });
                
                amplify.publish(E.GA4_EVENT, $.extend(true, {}, A.developer_portal.copy_query, {
                    label: $input.val()
                }));
            } catch (err) {
                console.error('Fallback: Oops, unable to copy', err);
            }
        },

        updateExcelSnippet: function() {
            var url = this.$el.find('#qb-generated-query').val();
            if (url) {
                // Add csv output type to the URL
                url += (url.indexOf('?') !== -1 ? '&' : '?') + 'output_type=csv';
            } else {
                url = "<URL_FROM_QUERY_BUILDER>";
            }
            
            var token = this.currentToken || this.$el.find('#access-token').text() || "<TOKEN_FROM_PORTAL>";

            var snippet = [
                'let',
                '    URL = "' + url + '",',
                '    token = "' + token + '",',
                '    Source = Csv.Document(Web.Contents(URL, [Headers=[Authorization="Bearer " & token]]), [Delimiter=",", Encoding=65001])',
                'in',
                '    Source'
            ].join('\n');

            this.$el.find('#excel-snippet').text(snippet);
        },

        copyExcelSnippet: function() {
            var snippet = this.$el.find('#excel-snippet').text();
            
            var textArea = document.createElement("textarea");
            textArea.value = snippet;
            document.body.appendChild(textArea);
            textArea.select();

            try {
                document.execCommand('copy');
                amplify.publish(E.NOTIFICATION_SUCCESS, { text: 'Power Query snippet copied to clipboard!' });
            } catch (err) {
                console.error('Fallback: Oops, unable to copy', err);
            }

            document.body.removeChild(textArea);
        }
    });

    return DeveloperPortalView;
});
