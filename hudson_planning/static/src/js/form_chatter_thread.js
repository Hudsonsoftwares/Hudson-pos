/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { setAttributes } from "@web/core/utils/xml";
import { FormCompiler } from "@web/views/form/form_compiler";

/**
 * <chatter thread_field="many2one_field" thread_model="its.model"/>: the
 * chatter shows the thread of the linked record when it is set (e.g. the field
 * service job of a shift), and the record's own thread otherwise.
 */
patch(FormCompiler.prototype, {
    compile(key, params) {
        const res = super.compile(...arguments);
        const chatter = this.templates[key]?.querySelector("chatter[thread_field][thread_model]");
        if (!chatter) {
            return res;
        }
        const linked = `__comp__.props.record.data.${chatter.getAttribute("thread_field")}`;
        const model = chatter.getAttribute("thread_model");
        for (const el of res.querySelectorAll("t[t-component='__comp__.mailComponents.Chatter']")) {
            setAttributes(el, {
                threadModel: `${linked} ? '${model}' : __comp__.props.record.resModel`,
                threadId: `(${linked} and ${linked}.id) or __comp__.props.record.resId or undefined`,
            });
        }
        return res;
    },
});
