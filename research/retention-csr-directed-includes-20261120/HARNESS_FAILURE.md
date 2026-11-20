This note preserves a CSR runner configuration failure. No executable or runtime evidence came from this attempt.

The custom base configuration define incorrectly named the enum selector e_bp_unicore_cfg instead of a packed configuration value. The custom schema macro then tried to access fields on an enum. The corrected runner uses bp_default_cfg_p, the exact struct value also used for the unicore baseline.
