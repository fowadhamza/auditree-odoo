/** @odoo-module **/

// Hooks for the notification animations in ../scss/ui_motion.scss.
// Nothing here changes behaviour; it only exposes state CSS cannot see.

import { useEffect, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { notificationService } from "@web/core/notifications/notification_service";
import { ActivityMenu } from "@mail/core/web/activity_menu";
import { MessagingMenu } from "@mail/core/web/messaging_menu";

// Toasts: mark the ones that close themselves, so only they get the
// countdown bar. The service deletes `sticky` from the props before the
// Notification component sees them, so it has to be read here.
patch(notificationService, {
    start() {
        const api = super.start(...arguments);
        return {
            ...api,
            add(message, options = {}) {
                if (!options.sticky) {
                    const className = `${options.className || ""} o_xn_toast_timed`.trim();
                    options = { ...options, className };
                }
                return api.add(message, options);
            },
        };
    },
});

/**
 * Returns a reactive {n} that increments only when getCount() goes up.
 * The systray icon is keyed by it, so it remounts (and the wobble replays)
 * on new messages/activities. Both counters start at 0 and are filled in
 * asynchronously after the menu mounts, so increases are ignored until
 * isReady() is true and the first ready value is taken as the baseline --
 * otherwise every page load would wobble. Decreases never bump.
 */
function useBumpOnIncrease(getCount, isReady) {
    const bump = useState({ n: 0 });
    let previous = getCount();
    let wasReady = isReady();
    useEffect(
        (count, ready) => {
            if (ready && wasReady && count > previous) {
                bump.n++;
            }
            previous = count;
            wasReady = ready;
        },
        () => [getCount(), isReady()]
    );
    return bump;
}

patch(MessagingMenu.prototype, {
    setup() {
        super.setup(...arguments);
        this.xnBump = useBumpOnIncrease(
            () => this.counter,
            () => this.store.isMessagingReady
        );
    },
});

patch(ActivityMenu.prototype, {
    setup() {
        // Created before super.setup(), which starts the first fetch. Reactive,
        // so the effect sees "loaded" even when the fetched count is 0 and
        // nothing else would re-render the menu.
        this.xnActivities = useState({ loaded: false });
        super.setup(...arguments);
        this.xnBump = useBumpOnIncrease(
            () => this.store.activityCounter,
            () => this.xnActivities.loaded
        );
    },

    async fetchSystrayActivities() {
        await super.fetchSystrayActivities(...arguments);
        this.xnActivities.loaded = true;
    },
});
