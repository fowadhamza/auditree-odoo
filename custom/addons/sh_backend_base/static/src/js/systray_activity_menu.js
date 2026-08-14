/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { session } from "@web/session";
import { onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
const { Component } = owl;

export class UserNotificationMenu extends Component {
  setup() {
    this.rpc = useService("rpc");
    this.busService = this.env.services.bus_service;
    this.notifications = this._getActivityData();
    this.action = useService("action");
    onWillStart(this.onWillStart);
    this._updateCounter();
  }

  async onWillStart() {
    this.busService.addEventListener(
      "notification",
      ({ detail: notifications }) => {
        for (var i = 0; i < notifications.length; i++) {
          var channel = notifications[i]["type"];
          if (channel == "sh.user.push.notifications") {
            this._getActivityData();
            this._updateCounter();
            $(document).find(".o_searchview_input").click();
            $(document).click();
          }
        }
      }
    );

    this.rpc(
      "/web/dataset/call_kw/sh.user.push.notification/has_bell_notification_enabled",
      {
        model: "sh.user.push.notification",
        method: "has_bell_notification_enabled",
        args: [],
        kwargs: {},
      }
    ).then(function (result) {
      $(".js_bell_notification");
      if (result.has_bell_notification_enabled) {
        $(".js_bell_notification").removeClass("d-none");
      } else {
        $(".js_bell_notification").addClass("d-none");
      }
    });
  }

  _onPushNotificationClick(notification) {
    // fetch the data from the button otherwise fetch the ones from the parent (.o_mail_preview).
    var data = notification;
    var context = {};
    var self = this;

    this.rpc("/web/dataset/call_kw/sh.user.push.notification/write", {
      model: "sh.user.push.notification",
      method: "write",
      args: [data.id, { msg_read: true }],
      kwargs: {},
    }).then(function () {
      self._getActivityData();
      self._updateCounter();
      if (data.res_model != "")
        self.action.doAction(
          {
            type: "ir.actions.act_window",
            name: data.res_model,
            res_model: data.res_model,
            views: [
              [false, "form"],
              [false, "tree"],
            ],
            search_view_id: [false],
            domain: [["id", "=", data.res_id]],
            res_id: data.res_id,
            context: context,
          },
          {
            clear_breadcrumbs: true,
          }
        );
    });
  }
  _onClickReadAllNotification(ev) {
    var self = this;

    this.rpc(
      "/web/dataset/call_kw/res.users/systray_get_firebase_all_notifications",
      {
        model: "res.users",
        method: "systray_get_firebase_all_notifications",
        args: [],
        kwargs: { context: session.user_context },
      }
    ).then(function (data, counter) {
      self._notifications = data[0];

      data[0].forEach((each_data) => {
        self
          .rpc("/web/dataset/call_kw/sh.user.push.notification/write", {
            model: "sh.user.push.notification",
            method: "write",
            args: [each_data.id, { msg_read: true }],
            kwargs: {},
          })
          .then(function () {
            self._getActivityData();
            self._updateCounter();
          });
      });
    });
  }
  _onClickAllNotification(ev) {
    this.action.doAction(
      {
        type: "ir.actions.act_window",
        name: "Notifications",
        res_model: "sh.user.push.notification",
        views: [[false, "list"]],
        view_mode: "list",
        target: "current",
        domain: [["user_id", "=", session.uid]],
      },
      {
        clear_breadcrumbs: true,
      }
    );
  }

  _updateCounter() {
    var counter = this._counter;
    if (counter > 0) {
      $(".o_notification_counter").text(counter);
    } else {
      $(".o_notification_counter").text("");
    }
  }

  _getActivityData() {
    var self = this;

    return this.rpc(
      "/web/dataset/call_kw/res.users/systray_get_firebase_notifications",
      {
        model: "res.users",
        method: "systray_get_firebase_notifications",
        args: [],
        kwargs: { context: session.user_context },
      }
    ).then(function (data, counter) {
      console.log("\n\n\n\n\n\n\n\n\n Dataa", data);
      self._notifications = data[0];
      self._counter = data[1];

      data[0].forEach((each_data) => {
        each_data["datetime"] = self.formatRelativeTime(each_data["datetime"]);
      });
      self._updateCounter();
      return data;
    });
  }

  _updateActivityPreview() {
    var self = this;
    self.notifications = self._notifications;
    $(".o_notification_systray_dropdown_items").removeClass("d-none");
  }

  async _onActivityMenuShow() {
    if ($(".o_notification_systray_dropdown").css("display") == "none") {
      $(".o_notification_systray_dropdown").css("display", "block");
    } else {
      $(".o_notification_systray_dropdown").css("display", "none");
    }
    await this._updateActivityPreview();
    this.render(true);
  }

  _onActivityActionClick(ev) {
    ev.stopPropagation();
    var actionXmlid = $(ev.currentTarget).data("action_xmlid");
    this.do_action(actionXmlid);
  }

  /**
   * Get particular model view to redirect on click of activity scheduled on that model.
   * @private
   * @param {string} model
   */
  _getActivityModelViewID(model) {
    return rpc.query({
      model: model,
      method: "get_activity_view_id",
    });
  }

  formatRelativeTime(dateTime) {
    const now = new Date();
    // Convert dateTime to a Date object
    dateTime = new Date(dateTime);

    const diffInSeconds = Math.floor((now - dateTime) / 1000);

    if (diffInSeconds < 60) {
      return _t("less than a minute ago");
    } else if (diffInSeconds < 120) {
      return _t("about a minute ago");
    } else if (diffInSeconds < 3600) {
      return _t(`${Math.floor(diffInSeconds / 60)} minutes ago`);
    } else if (diffInSeconds < 7200) {
      return _t("about an hour ago");
    } else if (diffInSeconds < 86400) {
      return _t(`${Math.floor(diffInSeconds / 3600)} hours ago`);
    } else if (diffInSeconds < 172800) {
      return _t("a day ago");
    } else if (diffInSeconds < 2592000) {
      return _t(`${Math.floor(diffInSeconds / 86400)} days ago`);
    } else if (diffInSeconds < 5184000) {
      return _t("about a month ago");
    } else if (diffInSeconds < 31536000) {
      return _t(`${Math.floor(diffInSeconds / 2592000)} months ago`);
    } else if (diffInSeconds < 63072000) {
      return _t("about a year ago");
    } else {
      return _t(`${Math.floor(diffInSeconds / 31536000)} years ago`);
    }
  }
}
UserNotificationMenu.template = "mail.systray.UserNotificationMenu";

export const systrayItem = {
  Component: UserNotificationMenu,
};

registry.category("systray").add("UserNotificationMenu", systrayItem);
