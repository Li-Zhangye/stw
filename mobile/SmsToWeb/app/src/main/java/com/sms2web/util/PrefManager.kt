package com.sms2web.util

import android.content.Context
import android.content.SharedPreferences

class PrefManager(context: Context) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences("sms2web", Context.MODE_PRIVATE)

    var serverAddress: String
        get() = prefs.getString("server_addr", "") ?: ""
        set(value) = prefs.edit().putString("server_addr", value).apply()

    var sessionId: String
        get() = prefs.getString("session_id", "") ?: ""
        set(value) = prefs.edit().putString("session_id", value).apply()

    var lastPhone: String
        get() = prefs.getString("last_phone", "") ?: ""
        set(value) = prefs.edit().putString("last_phone", value).apply()

    var privacyAgreed: Boolean
        get() = prefs.getBoolean("privacy_agreed", false)
        set(value) = prefs.edit().putBoolean("privacy_agreed", value).apply()

    var historySyncedAddr: String
        get() = prefs.getString("history_synced_addr", "") ?: ""
        set(value) = prefs.edit().putString("history_synced_addr", value).apply()

    // ---- Theme Properties ----

    var themeDark: Boolean
        get() = prefs.getBoolean("theme_dark", false)
        set(value) = prefs.edit().putBoolean("theme_dark", value).apply()

    var themeColor: String
        get() = prefs.getString("theme_color", "#4A90D9") ?: "#4A90D9"
        set(value) = prefs.edit().putString("theme_color", value).apply()

    var themeRadius: Int
        get() = prefs.getInt("theme_radius", 12)
        set(value) = prefs.edit().putInt("theme_radius", value).apply()

    var themeFontSize: Int
        get() = prefs.getInt("theme_font_size", 15)
        set(value) = prefs.edit().putInt("theme_font_size", value).apply()

    var themeCardBg: String
        get() = prefs.getString("theme_card_bg", "") ?: ""
        set(value) = prefs.edit().putString("theme_card_bg", value).apply()

    var themePageBg: String
        get() = prefs.getString("theme_page_bg", "") ?: ""
        set(value) = prefs.edit().putString("theme_page_bg", value).apply()

    var themeTextPrimary: String
        get() = prefs.getString("theme_text_primary", "") ?: ""
        set(value) = prefs.edit().putString("theme_text_primary", value).apply()

    var themeTextSecondary: String
        get() = prefs.getString("theme_text_secondary", "") ?: ""
        set(value) = prefs.edit().putString("theme_text_secondary", value).apply()

    var themeShadow: Int
        get() = prefs.getInt("theme_shadow", 2)
        set(value) = prefs.edit().putInt("theme_shadow", value).apply()

    var themeDensity: String
        get() = prefs.getString("theme_density", "standard") ?: "standard"
        set(value) = prefs.edit().putString("theme_density", value).apply()

    var themeAnimation: Boolean
        get() = prefs.getBoolean("theme_animation", true)
        set(value) = prefs.edit().putBoolean("theme_animation", value).apply()

    var themeGradient: Boolean
        get() = prefs.getBoolean("theme_gradient", false)
        set(value) = prefs.edit().putBoolean("theme_gradient", value).apply()

    var themeBlur: Boolean
        get() = prefs.getBoolean("theme_blur", false)
        set(value) = prefs.edit().putBoolean("theme_blur", value).apply()

    var themeTypeface: String
        get() = prefs.getString("theme_typeface", "default") ?: "default"
        set(value) = prefs.edit().putString("theme_typeface", value).apply()

    var themeFontPath: String
        get() = prefs.getString("theme_font_path", "") ?: ""
        set(value) = prefs.edit().putString("theme_font_path", value).apply()

    var themeSyncServer: Boolean
        get() = prefs.getBoolean("theme_sync_server", false)
        set(value) = prefs.edit().putBoolean("theme_sync_server", value).apply()

    fun clearSession() {
        prefs.edit().remove("session_id").apply()
    }

    var language: String
        get() = prefs.getString("language", "zh") ?: "zh"
        set(value) = prefs.edit().putString("language", value).apply()

    fun clearAll() {
        prefs.edit().clear().apply()
    }
}
