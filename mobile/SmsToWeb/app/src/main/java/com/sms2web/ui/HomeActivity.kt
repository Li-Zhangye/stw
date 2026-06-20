package com.sms2web.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.res.Configuration
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.*
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AppCompatDelegate
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import com.sms2web.R
import com.sms2web.SmsToWebApp
import com.sms2web.api.ApiClient
import com.sms2web.service.SmsForwardService
import com.sms2web.util.FileLogger
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.ExecutorService

class HomeActivity : AppCompatActivity() {
    private val executor = Executors.newCachedThreadPool()
    private lateinit var app: SmsToWebApp
    private val smsList = mutableListOf<JSONObject>()
    private var currentTab = "history"
    private var lastMaxId = 0
    private val handler = Handler(Looper.getMainLooper())
    private var polling = false
    private var loadingSms = false
    private var searchQuery = ""
    private val pickFontLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == RESULT_OK && result.data?.data != null) {
            handleFontPicked(result.data?.data!!)
        }
    }

    private lateinit var listView: ListView
    private lateinit var adapter: SmsAdapter
    private lateinit var emptyView: View
    private lateinit var serviceStatus: TextView
    private lateinit var tabHistory: TextView
    private lateinit var tabRead: TextView
    private lateinit var tabUnread: TextView
    private lateinit var unreadBadge: TextView
    private lateinit var deviceOfflineBanner: View
    private lateinit var deviceStatusLabel: TextView

    private lateinit var rootLayout: View

    override fun onCreate(savedInstanceState: Bundle?) {
        app = application as SmsToWebApp
        if (app.prefs.themeDark) {
            AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_YES)
        } else {
            AppCompatDelegate.setDefaultNightMode(AppCompatDelegate.MODE_NIGHT_NO)
        }
        applyLanguage(app.prefs.language)
        super.onCreate(savedInstanceState)
        FileLogger.i("HomeActivity", "onCreate")
        setContentView(R.layout.activity_home)

        listView = findViewById(R.id.smsListView)
        emptyView = findViewById(R.id.emptyView)
        serviceStatus = findViewById(R.id.serviceStatus)
        tabHistory = findViewById(R.id.tabHistory)
        tabRead = findViewById(R.id.tabRead)
        tabUnread = findViewById(R.id.tabUnread)
        unreadBadge = findViewById(R.id.unreadBadge)
        deviceOfflineBanner = findViewById(R.id.deviceOfflineBanner)
        deviceStatusLabel = findViewById(R.id.deviceStatusLabel)
        rootLayout = findViewById(android.R.id.content)

        adapter = SmsAdapter()
        listView.adapter = adapter

        applyTheme()

        findViewById<ImageButton>(R.id.refreshBtn).setOnClickListener { loadSms() }

        listView.onItemClickListener = AdapterView.OnItemClickListener { _, _, position, _ ->
            val filtered = filteredList()
            if (position >= filtered.size) return@OnItemClickListener
            val item = filtered[position]
            val id = item.optInt("id")
            if (id > 0 && item.optInt("is_read") == 0) {
                markRead(id)
            }
            showSmsDetail(item)
        }

        listView.onItemLongClickListener = AdapterView.OnItemLongClickListener { _, _, position, _ ->
            val filtered = filteredList()
            if (position >= filtered.size) return@OnItemLongClickListener true
            showSmsActions(filtered[position])
            true
        }

        findViewById<ImageButton>(R.id.settingsBtn).setOnClickListener { showSettingsDialog() }

        tabHistory.setOnClickListener { switchTab("history") }
        tabRead.setOnClickListener { switchTab("read") }
        tabUnread.setOnClickListener { switchTab("unread") }

        checkLoginAndStart()
    }

    @Suppress("DEPRECATION")
    private fun applyLanguage(lang: String) {
        val locale = when (lang) {
            "zh-tw" -> java.util.Locale("zh", "TW")
            "en" -> java.util.Locale("en")
            else -> java.util.Locale("zh", "CN")
        }
        java.util.Locale.setDefault(locale)
        val config = Configuration(resources.configuration)
        config.setLocale(locale)
        resources.updateConfiguration(config, resources.displayMetrics)
    }

    private fun applyTheme() {
        val p = app.prefs
        val bgColor = if (p.themePageBg.isNotEmpty()) android.graphics.Color.parseColor(p.themePageBg) else null
        if (bgColor != null) {
            rootLayout.setBackgroundColor(bgColor)
        }
        if (p.themeGradient) {
            val mainColor = android.graphics.Color.parseColor(p.themeColor)
            val darkColor = android.graphics.Color.parseColor(
                if (p.themeDark) "#1A1A2E" else "#F0F4F8"
            )
            val gradient = android.graphics.drawable.GradientDrawable(
                android.graphics.drawable.GradientDrawable.Orientation.TOP_BOTTOM,
                intArrayOf(mainColor, darkColor)
            )
            rootLayout.background = gradient
        }
        if (!p.themeAnimation) {
            listView.layoutAnimation = null
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        polling = false
        handler.removeCallbacksAndMessages(null)
        executor.shutdownNow()
        FileLogger.i("HomeActivity", "onDestroy")
    }

    private fun switchTab(tab: String) {
        currentTab = tab
        val active = R.drawable.tab_active_bg
        val inactive = android.R.color.transparent
        val activeColor = getColorCompat(R.color.tab_active)
        val inactiveColor = getColorCompat(R.color.tab_inactive)

        tabHistory.setBackgroundResource(if (tab == "history") active else inactive)
        tabRead.setBackgroundResource(if (tab == "read") active else inactive)
        tabUnread.setBackgroundResource(if (tab == "unread") active else inactive)
        tabHistory.setTextColor(if (tab == "history") activeColor else inactiveColor)
        tabRead.setTextColor(if (tab == "read") activeColor else inactiveColor)
        tabUnread.setTextColor(if (tab == "unread") activeColor else inactiveColor)
        refreshDisplay()
    }

    private fun getColorCompat(id: Int): Int {
        return ContextCompat.getColor(this, id)
    }

    private fun checkLoginAndStart() {
        executor.submit {
            try {
                val result = ApiClient.post("/api/auth/user/info", JSONObject(), app.prefs.sessionId)
                handler.post {
                    if (result.optBoolean("success", false)) {
                        startForwardingService()
                        startPolling()
                        startHeartbeat()
                        loadSms()
                    } else {
                        Toast.makeText(this, "请先登录", Toast.LENGTH_SHORT).show()
                        goLogin()
                    }
                }
            } catch (e: Exception) {
                FileLogger.e("HomeActivity", "login check failed", e)
                handler.post {
                    Toast.makeText(this, "网络错误: ${e.message}", Toast.LENGTH_SHORT).show()
                    goLogin()
                }
            }
        }
    }

    private fun startForwardingService() {
        try {
            val intent = Intent(this, SmsForwardService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent)
            else startService(intent)
            val syncIntent = Intent(this, SmsForwardService::class.java).apply {
                action = SmsForwardService.ACTION_SYNC_HISTORY
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(syncIntent)
            else startService(syncIntent)
            serviceStatus.text = "服务运行中"
            serviceStatus.setTextColor(getColorCompat(R.color.success))
        } catch (e: Exception) {
            serviceStatus.text = "服务启动失败"
            serviceStatus.setTextColor(getColorCompat(R.color.error))
            FileLogger.e("HomeActivity", "service start failed", e)
        }
    }

    private fun goLogin() {
        startActivity(Intent(this, LoginActivity::class.java))
        finish()
    }

    private fun startPolling() {
        polling = true
        handler.postDelayed(object : Runnable {
            override fun run() {
                if (!polling) return
                loadSms()
                handler.postDelayed(this, 5000)
            }
        }, 5000)
    }

    private fun startHeartbeat() {
        handler.postDelayed(object : Runnable {
            override fun run() {
                if (!polling) return
                executor.submit {
                    try {
                        val result = ApiClient.post("/api/heartbeat", JSONObject(), app.prefs.sessionId)
                        val online = result.optBoolean("online", false)
                        handler.post { updateDeviceStatus(online) }
                    } catch (e: Exception) {
                        FileLogger.e("HomeActivity", "heartbeat error", e)
                    }
                }
                handler.postDelayed(this, 30000)
            }
        }, 30000)
    }

    private fun updateDeviceStatus(online: Boolean) {
        deviceOfflineBanner.visibility = if (online) View.GONE else View.VISIBLE
        deviceStatusLabel.visibility = View.VISIBLE
        deviceStatusLabel.text = if (online) "在线" else "离线"
        deviceStatusLabel.setTextColor(
            if (online) getColorCompat(R.color.success) else getColorCompat(R.color.error)
        )
    }

    private fun loadSms() {
        if (loadingSms) return
        loadingSms = true
        executor.submit {
            try {
                val url = "/api/sms/list?limit=200" + if (lastMaxId > 0) "&since_id=$lastMaxId&wait=25" else ""
                val result = ApiClient.get(url, app.prefs.sessionId)
                handler.post {
                    try {
                        if (result.optBoolean("success", false)) {
                            val arr = result.optJSONArray("sms") ?: JSONArray()
                            var newCount = 0
                            for (i in 0 until arr.length()) {
                                val msg = arr.getJSONObject(i)
                                val id = msg.optInt("id")
                                if (id > lastMaxId) lastMaxId = id
                                if (smsList.none { it.optInt("id") == id }) {
                                    smsList.add(msg)
                                }
                            }
                            smsList.sortByDescending { it.optInt("id") }
                            val unread = result.optInt("unread", 0)
                            if (newCount > 0) {
                                FileLogger.i("HomeActivity", "loaded $newCount new")
                                showNewSmsNotification(newCount)
                            }
                            updateBadge(unread)
                            refreshDisplay()
                        }
                    } finally {
                        loadingSms = false
                    }
                }
            } catch (e: Exception) {
                FileLogger.e("HomeActivity", "load sms error", e)
                loadingSms = false
            }
        }
    }

    private fun showNewSmsNotification(count: Int) {
        Toast.makeText(this, "新短信 ($count 条)", Toast.LENGTH_SHORT).show()
    }

    private fun filteredList(): List<JSONObject> {
        val base = when (currentTab) {
            "read" -> smsList.filter { it.optInt("is_read") == 1 }
            "unread" -> smsList.filter { it.optInt("is_read") == 0 }
            else -> smsList.toList()
        }
        return if (searchQuery.isNotEmpty()) {
            base.filter { msg ->
                msg.optString("sender").contains(searchQuery, ignoreCase = true) ||
                msg.optString("content").contains(searchQuery, ignoreCase = true)
            }
        } else base
    }

    private fun refreshDisplay() {
        val filtered = filteredList()
        adapter.update(filtered)
        emptyView.visibility = if (filtered.isEmpty()) View.VISIBLE else View.GONE
        listView.visibility = if (filtered.isEmpty()) View.GONE else View.VISIBLE
    }

    private fun updateBadge(count: Int) {
        if (count > 0) {
            unreadBadge.text = count.toString()
            unreadBadge.visibility = View.VISIBLE
        } else {
            unreadBadge.visibility = View.GONE
        }
    }

    private fun markRead(id: Int) {
        executor.submit {
            try {
                val body = JSONObject().apply { put("ids", JSONArray().put(id)) }
                ApiClient.post("/api/sms/mark-read", body, app.prefs.sessionId)
                handler.post {
                    for (msg in smsList) {
                        if (msg.optInt("id") == id) {
                            msg.put("is_read", 1)
                            break
                        }
                    }
                    refreshDisplay()
                    updateBadge(smsList.count { it.optInt("is_read") == 0 })
                }
            } catch (e: Exception) {
                FileLogger.e("HomeActivity", "markRead error", e)
            }
        }
    }

    private fun showSmsDetail(msg: JSONObject) {
        val sender = msg.optString("sender", "")
        val content = msg.optString("content", "")
        val time = msg.optString("received_at", "").take(19)
        AlertDialog.Builder(this)
            .setTitle(sender)
            .setMessage("$content\n\n---\n$time")
            .setPositiveButton("复制") { _, _ -> copyToClipboard(content) }
            .setNeutralButton("关闭", null)
            .show()
    }

    private fun showSmsActions(msg: JSONObject) {
        val sender = msg.optString("sender", "")
        val content = msg.optString("content", "")
        val id = msg.optInt("id")
        val isRead = msg.optInt("is_read") == 0
        val items = arrayOf("复制发件人", "复制内容", if (isRead) "标为已读" else "标为未读", "删除")
        AlertDialog.Builder(this)
            .setTitle(sender)
            .setItems(items) { _, which ->
                when (which) {
                    0 -> copyToClipboard(sender)
                    1 -> copyToClipboard(content)
                    2 -> toggleRead(id, isRead)
                    3 -> deleteSms(id)
                }
            }
            .show()
    }

    private fun deleteSms(id: Int) {
        AlertDialog.Builder(this)
            .setTitle("删除短信")
            .setMessage("确定删除此短信？此操作不可撤销。")
            .setPositiveButton("删除") { _, _ ->
                executor.submit {
                    try {
                        val body = JSONObject().apply { put("ids", JSONArray().put(id)) }
                        val result = ApiClient.post("/api/sms/delete", body, app.prefs.sessionId)
                        handler.post {
                            if (result.optBoolean("success", false)) {
                                smsList.removeAll { it.optInt("id") == id }
                                refreshDisplay()
                                updateBadge(smsList.count { it.optInt("is_read") == 0 })
                                Toast.makeText(this, result.optString("message", "已删除"), Toast.LENGTH_SHORT).show()
                            } else {
                                Toast.makeText(this, result.optString("message", "删除失败"), Toast.LENGTH_SHORT).show()
                            }
                        }
                    } catch (e: Exception) {
                        FileLogger.e("HomeActivity", "delete error", e)
                        handler.post { Toast.makeText(this, "网络错误", Toast.LENGTH_SHORT).show() }
                    }
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun toggleRead(id: Int, markAsRead: Boolean) {
        if (markAsRead) { markRead(id); return }
        executor.submit {
            try {
                val body = JSONObject().apply { put("ids", JSONArray().put(id)) }
                ApiClient.post("/api/sms/mark-unread", body, app.prefs.sessionId)
                handler.post {
                    for (msg in smsList) {
                        if (msg.optInt("id") == id) { msg.put("is_read", 0); break }
                    }
                    refreshDisplay()
                    updateBadge(smsList.count { it.optInt("is_read") == 0 })
                }
            } catch (e: Exception) {
                FileLogger.e("HomeActivity", "toggleRead error", e)
            }
        }
    }

    private fun copyToClipboard(text: String) {
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        cm.setPrimaryClip(ClipData.newPlainText("sms", text))
        Toast.makeText(this, "已复制到剪贴板", Toast.LENGTH_SHORT).show()
    }

    private fun markAllRead() {
        executor.submit {
            try {
                val unreadIds = JSONArray()
                for (msg in smsList) {
                    if (msg.optInt("is_read") == 0) unreadIds.put(msg.optInt("id"))
                }
                if (unreadIds.length() == 0) {
                    handler.post { Toast.makeText(this, "没有未读短信", Toast.LENGTH_SHORT).show() }
                    return@submit
                }
                val body = JSONObject().apply { put("ids", unreadIds) }
                val result = ApiClient.post("/api/sms/mark-read", body, app.prefs.sessionId)
                handler.post {
                    if (result.optBoolean("success", false)) {
                        for (msg in smsList) msg.put("is_read", 1)
                        refreshDisplay()
                        updateBadge(0)
                        Toast.makeText(this, result.optString("message", "已全部标为已读"), Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                FileLogger.e("HomeActivity", "markAllRead error", e)
                handler.post { Toast.makeText(this, "网络错误", Toast.LENGTH_SHORT).show() }
            }
        }
    }

    // ----- Settings -----

    private fun showSettingsDialog() {
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 16, 24, 16)
        }

        fun addItem(text: String, onClick: () -> Unit) {
            val btn = Button(this@HomeActivity).apply {
                this.text = text
                setBackgroundResource(R.drawable.bg_card)
                textSize = 14f
                setTextColor(ContextCompat.getColor(this@HomeActivity, R.color.text_primary))
                gravity = Gravity.START or Gravity.CENTER_VERTICAL
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    (48 * resources.displayMetrics.density).toInt()
                ).apply { topMargin = 4 }
                setOnClickListener { onClick() }
            }
            layout.addView(btn)
        }

        fun addDivider() {
            val div = View(this@HomeActivity).apply {
                setBackgroundColor(ContextCompat.getColor(this@HomeActivity, R.color.divider))
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    1
                ).apply { topMargin = 8; bottomMargin = 4 }
            }
            layout.addView(div)
        }

        addItem("账号信息") { showAccountInfoDialog() }
        addDivider()
        addItem("修改密码") { showChangePasswordDialog() }
        addItem("邮箱验证码改密") { showChangePwdByEmailDialog() }
        addDivider()
        addItem("搜索短信") { showSearchDialog() }
        addItem("全部标为已读") { markAllRead() }
        addItem("导出短信") { exportSms() }
        addDivider()
        addItem("切换用户") { switchUser() }
        addItem("更换服务器") { changeServer() }
        addItem("退出登录") { logout() }
        addDivider()
        addItem("主题设置") { showThemeDialog() }
        addItem("关于") { showAboutDialog() }

        AlertDialog.Builder(this)
            .setTitle("设置")
            .setView(layout)
            .setNegativeButton("关闭", null)
            .show()
    }

    private fun showAccountInfoDialog() {
        executor.submit {
            try {
                val result = ApiClient.post("/api/auth/user/info", JSONObject(), app.prefs.sessionId)
                handler.post {
                    if (result.optBoolean("success", false)) {
                        val d = result.optJSONObject("data")
                        if (d == null) {
                            Toast.makeText(this, "获取信息失败", Toast.LENGTH_SHORT).show(); return@post
                        }
                        val info = """
                            手机号: ${d.optString("phone", "-")}
                            邮箱: ${d.optString("email", "-")}
                            注册时间: ${d.optString("registered_at", "-")}
                            最后登录: ${d.optString("last_login_at", "首次登录")}
                        """.trimIndent()
                        AlertDialog.Builder(this)
                            .setTitle("账号信息")
                            .setMessage(info)
                            .setPositiveButton("确定", null)
                            .show()
                    } else {
                        Toast.makeText(this, "获取信息失败", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                FileLogger.e("HomeActivity", "account info error", e)
                handler.post { Toast.makeText(this, "网络错误", Toast.LENGTH_SHORT).show() }
            }
        }
    }

    private fun showChangePasswordDialog() {
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 20, 40, 20)
        }
        val curPwd = EditText(this).apply {
            hint = "当前密码"
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        val newPwd = EditText(this).apply {
            hint = "新密码（8-32位，含数字/大小写/特殊符号）"
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        val confirmPwd = EditText(this).apply {
            hint = "确认新密码"
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        layout.addView(curPwd)
        layout.addView(newPwd)
        layout.addView(confirmPwd)
        val params = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = 12 }
        for (i in 0 until layout.childCount) layout.getChildAt(i).layoutParams = params

        AlertDialog.Builder(this)
            .setTitle("修改密码")
            .setView(layout)
            .setPositiveButton("确认修改") { _, _ ->
                val cur = curPwd.text.toString()
                val pwd = newPwd.text.toString()
                val confirm = confirmPwd.text.toString()
                if (cur.isEmpty() || pwd.isEmpty() || confirm.isEmpty()) {
                    Toast.makeText(this, "请填写所有字段", Toast.LENGTH_SHORT).show(); return@setPositiveButton
                }
                if (pwd != confirm) {
                    Toast.makeText(this, "两次密码不一致", Toast.LENGTH_SHORT).show(); return@setPositiveButton
                }
                val valid = pwd.any { it.isDigit() } && pwd.any { it.isLowerCase() } && pwd.any { it.isUpperCase() } && pwd.any { "!@#\$%^&*()_+-=[]{}|;':\",.<>?/~`".contains(it) } && pwd.length in 8..32
                if (!valid) {
                    Toast.makeText(this, "密码必须包含数字、大小写字母、特殊符号，8-32位", Toast.LENGTH_LONG).show(); return@setPositiveButton
                }
                executor.submit {
                    try {
                        val body = JSONObject().apply { put("currentPassword", cur); put("newPassword", pwd) }
                        val result = ApiClient.post("/api/auth/change-password", body, app.prefs.sessionId)
                        handler.post {
                            Toast.makeText(this, result.optString("message", "修改成功"), Toast.LENGTH_SHORT).show()
                        }
                    } catch (e: Exception) {
                        FileLogger.e("HomeActivity", "change pwd error", e)
                        handler.post { Toast.makeText(this, "网络错误", Toast.LENGTH_SHORT).show() }
                    }
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }

    // email code change password (new feature)
    private fun showChangePwdByEmailDialog() {
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 20, 40, 20)
        }
        val codeInput = EditText(this).apply {
            hint = "邮箱验证码"
            inputType = android.text.InputType.TYPE_CLASS_NUMBER
            maxLines = 1
        }
        val newPwd = EditText(this).apply {
            hint = "新密码（8-32位，含数字/大小写/特殊符号）"
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        val confirmPwd = EditText(this).apply {
            hint = "确认新密码"
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        val sendBtn = Button(this).apply {
            text = "发送验证码到邮箱"
            setTextColor(getColorCompat(R.color.primary))
            setOnClickListener {
                executor.submit {
                    try {
                        val body = JSONObject().apply { put("phone", app.prefs.lastPhone) }
                        val result = ApiClient.post("/api/auth/login/send-email-code", body, app.prefs.sessionId)
                        handler.post {
                            Toast.makeText(this@HomeActivity, result.optString("message", "验证码已发送"), Toast.LENGTH_SHORT).show()
                        }
                    } catch (e: Exception) {
                        handler.post { Toast.makeText(this@HomeActivity, "网络错误", Toast.LENGTH_SHORT).show() }
                    }
                }
            }
        }
        layout.addView(sendBtn)
        layout.addView(codeInput)
        layout.addView(newPwd)
        layout.addView(confirmPwd)
        val params = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = 12 }
        for (i in 0 until layout.childCount) layout.getChildAt(i).layoutParams = params

        AlertDialog.Builder(this)
            .setTitle("邮箱验证码改密")
            .setView(layout)
            .setPositiveButton("确认修改") { _, _ ->
                val code = codeInput.text.toString().trim()
                val pwd = newPwd.text.toString()
                val confirm = confirmPwd.text.toString()
                if (code.isEmpty() || pwd.isEmpty() || confirm.isEmpty()) {
                    Toast.makeText(this, "请填写所有字段", Toast.LENGTH_SHORT).show(); return@setPositiveButton
                }
                if (pwd != confirm) {
                    Toast.makeText(this, "两次密码不一致", Toast.LENGTH_SHORT).show(); return@setPositiveButton
                }
                val valid = pwd.any { it.isDigit() } && pwd.any { it.isLowerCase() } && pwd.any { it.isUpperCase() } && pwd.any { "!@#\$%^&*()_+-=[]{}|;':\",.<>?/~`".contains(it) } && pwd.length in 8..32
                if (!valid) {
                    Toast.makeText(this, "密码必须包含数字、大小写字母、特殊符号，8-32位", Toast.LENGTH_LONG).show(); return@setPositiveButton
                }
                executor.submit {
                    try {
                        val body = JSONObject().apply { put("emailCode", code); put("newPassword", pwd) }
                        val result = ApiClient.post("/api/auth/change-password-by-email", body, app.prefs.sessionId)
                        handler.post {
                            Toast.makeText(this@HomeActivity, result.optString("message", "修改成功"), Toast.LENGTH_SHORT).show()
                        }
                    } catch (e: Exception) {
                        FileLogger.e("HomeActivity", "email change pwd error", e)
                        handler.post { Toast.makeText(this, "网络错误", Toast.LENGTH_SHORT).show() }
                    }
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }

    // search dialog (new feature)
    private fun showSearchDialog() {
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 20, 40, 20)
        }
        val searchInput = EditText(this).apply {
            hint = "搜索发件人或短信内容"
            setText(searchQuery)
        }
        layout.addView(searchInput)
        AlertDialog.Builder(this)
            .setTitle("搜索短信")
            .setView(layout)
            .setPositiveButton("搜索") { _, _ ->
                searchQuery = searchInput.text.toString().trim()
                refreshDisplay()
            }
            .setNegativeButton("清除") { _, _ ->
                searchQuery = ""
                refreshDisplay()
            }
            .setNeutralButton("取消", null)
            .show()
    }

    // export SMS (new feature)
    private fun exportSms() {
        Toast.makeText(this, "正在导出...", Toast.LENGTH_SHORT).show()
        executor.submit {
            try {
                val json = ApiClient.get("/api/sms/export", app.prefs.sessionId)
                val text = json.toString(2)
                handler.post {
                    val intent = Intent(Intent.ACTION_SEND).apply {
                        type = "text/plain"
                        putExtra(Intent.EXTRA_TEXT, text)
                        putExtra(Intent.EXTRA_SUBJECT, "短信导出备份")
                    }
                    startActivity(Intent.createChooser(intent, "导出短信"))
                }
            } catch (e: Exception) {
                FileLogger.e("HomeActivity", "export error", e)
                handler.post { Toast.makeText(this, "导出失败: ${e.message}", Toast.LENGTH_SHORT).show() }
            }
        }
    }

    private fun switchUser() {
        AlertDialog.Builder(this)
            .setTitle("切换用户")
            .setMessage("退出当前账号，跳转到登录页。\n可选择其他账号重新登录，服务器地址保持不变。")
            .setPositiveButton("退出并切换") { _, _ ->
                executor.submit {
                    try { ApiClient.post("/api/auth/logout", JSONObject(), app.prefs.sessionId) } catch (_: Exception) {}
                    handler.post {
                        app.prefs.clearSession()
                        polling = false
                        goLogin()
                    }
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun changeServer() {
        val input = EditText(this).apply {
            hint = "IP:端口"
            setText(app.prefs.serverAddress)
            inputType = android.text.InputType.TYPE_CLASS_TEXT
        }
        input.layoutParams = ViewGroup.MarginLayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { setMargins(40, 0, 40, 0) }
        AlertDialog.Builder(this)
            .setTitle("更换服务器")
            .setMessage("修改后将断开当前连接，返回首页重新连接新服务器。")
            .setView(input)
            .setPositiveButton("确认更换") { _, _ ->
                val addr = input.text.toString().trim()
                if (addr.isEmpty()) {
                    Toast.makeText(this, "地址不能为空", Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }
                app.prefs.serverAddress = addr
                ApiClient.baseUrl = addr
                Toast.makeText(this, "服务器地址已更新，请重新连接", Toast.LENGTH_SHORT).show()
                polling = false
                goLogin()
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun logout() {
        AlertDialog.Builder(this)
            .setTitle("退出登录")
            .setMessage("清除所有本地数据（包括服务器地址和登录信息），完全退出到初始页。\n下次使用需重新输入服务器地址。")
            .setPositiveButton("确认退出") { _, _ ->
                executor.submit {
                    try { ApiClient.post("/api/auth/logout", JSONObject(), app.prefs.sessionId) } catch (_: Exception) {}
                    handler.post {
                        app.prefs.clearAll()
                        polling = false
                        Toast.makeText(this, "已完全退出", Toast.LENGTH_SHORT).show()
                        goLogin()
                    }
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }

    private fun showThemeDialog() {
        val scroll = ScrollView(this@HomeActivity)
        val layout = LinearLayout(this@HomeActivity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 20, 32, 20)
        }

        fun sectionTitle(text: String) {
            layout.addView(TextView(this@HomeActivity).apply {
                this.text = text
                textSize = 13f
                setTypeface(null, android.graphics.Typeface.BOLD)
                setTextColor(getColorCompat(R.color.tab_active))
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT
                ).apply { topMargin = 18; bottomMargin = 6 }
            })
        }

        fun themeToggle(label: String, subtitle: String, isOn: Boolean, onToggle: (Boolean) -> Unit) {
            val row = LinearLayout(this@HomeActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT
                ).apply { topMargin = 4; bottomMargin = 4 }
            }
            val textWrap = LinearLayout(this@HomeActivity).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            }
            textWrap.addView(TextView(this@HomeActivity).apply { text = label; textSize = 15f; setTextColor(getColorCompat(R.color.text_primary)) })
            textWrap.addView(TextView(this@HomeActivity).apply { text = subtitle; textSize = 12f; setTextColor(getColorCompat(R.color.text_hint)) })
            row.addView(textWrap)
            val toggle = Switch(this@HomeActivity).apply {
                isChecked = isOn
                setOnCheckedChangeListener { _, checked -> onToggle(checked) }
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT
                ).apply { marginStart = 16 }
            }
            row.addView(toggle)
            layout.addView(row)
        }

        fun seekSlider(label: String, value: Int, max: Int, suffix: String, onChange: (Int) -> Unit) {
            layout.addView(TextView(this@HomeActivity).apply {
                text = "$label: $value$suffix"
                textSize = 14f; setTextColor(getColorCompat(R.color.text_primary))
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT
                ).apply { topMargin = 8; bottomMargin = 4 }
            })
            val seek = SeekBar(this@HomeActivity).apply {
                this.max = max
                progress = value
                setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                    override fun onProgressChanged(sb: SeekBar?, p: Int, fromUser: Boolean) {}
                    override fun onStartTrackingTouch(sb: SeekBar?) {}
                    override fun onStopTrackingTouch(sb: SeekBar?) { onChange(progress) }
                })
            }
            layout.addView(seek)
        }

        var selectedColor = app.prefs.themeColor

        // ===== 1. 深色模式 =====
        sectionTitle("基础")
        themeToggle("深色模式", "切换深色/浅色主题", app.prefs.themeDark) { checked ->
            app.prefs.themeDark = checked; recreate()
        }

        // ===== 2. 主题色 =====
        sectionTitle("主题颜色")
        val presets = listOf(
            "#4A90D9" to "默认蓝", "#00B894" to "翡翠绿", "#E17055" to "日落橙",
            "#6C5CE7" to "紫色", "#FD79A8" to "樱花粉", "#00CEC9" to "青色",
            "#E74C3C" to "中国红", "#FDCB6E" to "香槟黄", "#2D3436" to "酷黑",
        )
        val colorRow = LinearLayout(this@HomeActivity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_HORIZONTAL
        }
        for ((code, _) in presets) {
            val dot = View(this@HomeActivity).apply {
                val size = (36 * resources.displayMetrics.density).toInt()
                layoutParams = LinearLayout.LayoutParams(size, size).apply { marginEnd = 6 }
                background = android.graphics.drawable.GradientDrawable().apply {
                    shape = android.graphics.drawable.GradientDrawable.OVAL
                    setColor(android.graphics.Color.parseColor(code))
                    setStroke(3, if (code.equals(selectedColor, ignoreCase = true)) android.graphics.Color.WHITE else android.graphics.Color.TRANSPARENT)
                }
                setOnClickListener { selectedColor = code; app.prefs.themeColor = code; recreate() }
            }
            colorRow.addView(dot)
        }
        layout.addView(colorRow)
        // custom color input
        val customRow = LinearLayout(this@HomeActivity).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = 6 }
        }
        val hexInput = EditText(this@HomeActivity).apply {
            hint = "#HEX 例如 #FF5733"
            textSize = 14f
            inputType = android.text.InputType.TYPE_CLASS_TEXT
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            setText(app.prefs.themeColor)
        }
        customRow.addView(hexInput)
        val applyBtn = Button(this@HomeActivity).apply {
            text = "应用"
            textSize = 13f
            setOnClickListener {
                try {
                    val c = hexInput.text.toString().trim()
                    if (c.matches(Regex("^#[0-9A-Fa-f]{6}$"))) {
                        app.prefs.themeColor = c; recreate()
                    } else {
                        Toast.makeText(this@HomeActivity, "无效颜色格式，使用 #RRGGBB", Toast.LENGTH_SHORT).show()
                    }
                } catch (_: Exception) {}
            }
        }
        customRow.addView(applyBtn)
        layout.addView(TextView(this@HomeActivity).apply {
            text = "自定义颜色"; textSize = 12f; setTextColor(getColorCompat(R.color.text_hint))
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = 4 }
        })
        layout.addView(customRow)

        // ===== 3. 卡片背景色 + 页面背景色 + 文字色 =====
        sectionTitle("自定义颜色覆盖")
        fun colorEdit(label: String, current: String, save: (String) -> Unit) {
            val row = LinearLayout(this@HomeActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = 4 }
            }
            row.addView(TextView(this@HomeActivity).apply {
                text = label; textSize = 14f; setTextColor(getColorCompat(R.color.text_primary))
                layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { gravity = Gravity.CENTER_VERTICAL; marginEnd = 8 }
            })
            val ed = EditText(this@HomeActivity).apply {
                hint = "留空=默认"
                setText(if (current.isNotEmpty()) current else "")
                textSize = 13f
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
                inputType = android.text.InputType.TYPE_CLASS_TEXT
            }
            row.addView(ed)
            val btn = Button(this@HomeActivity).apply {
                text = "✓"
                textSize = 12f
                setOnClickListener {
                    val v = ed.text.toString().trim()
                    if (v.isEmpty() || v.matches(Regex("^#[0-9A-Fa-f]{6}$"))) {
                        save(v); recreate()
                    } else {
                        Toast.makeText(this@HomeActivity, "格式: #RRGGBB", Toast.LENGTH_SHORT).show()
                    }
                }
            }
            row.addView(btn)
            layout.addView(row)
        }
        colorEdit("卡片背景", app.prefs.themeCardBg) { app.prefs.themeCardBg = it }
        colorEdit("页面背景", app.prefs.themePageBg) { app.prefs.themePageBg = it }
        colorEdit("主文字色", app.prefs.themeTextPrimary) { app.prefs.themeTextPrimary = it }
        colorEdit("次文字色", app.prefs.themeTextSecondary) { app.prefs.themeTextSecondary = it }

        // ===== 4. 圆角 =====
        sectionTitle("圆角")
        seekSlider("卡片圆角", app.prefs.themeRadius, 30, "dp") {
            app.prefs.themeRadius = it; recreate()
        }

        // ===== 5. 阴影 =====
        sectionTitle("阴影")
        seekSlider("卡片阴影", app.prefs.themeShadow, 20, "dp") {
            app.prefs.themeShadow = it; recreate()
        }

        // ===== 6. 字号 =====
        sectionTitle("字号")
        seekSlider("消息字体大小", app.prefs.themeFontSize, 24, "sp") {
            app.prefs.themeFontSize = it; recreate()
        }

        // ===== 7. 布局密度 =====
        sectionTitle("布局密度")
        val densityOpts = listOf("compact" to "紧凑", "standard" to "标准", "comfortable" to "宽松")
        val densityRow = LinearLayout(this@HomeActivity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }
        for ((value, label) in densityOpts) {
            val isSelected = app.prefs.themeDensity == value
            val btn = Button(this@HomeActivity).apply {
                text = label
                textSize = 13f
                setTextColor(getColorCompat(if (isSelected) R.color.white else R.color.text_primary))
                setBackgroundResource(if (isSelected) R.drawable.tab_active_bg else R.drawable.bg_card)
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { marginEnd = 4 }
                setOnClickListener { app.prefs.themeDensity = value; recreate() }
            }
            densityRow.addView(btn)
        }
        layout.addView(densityRow)

        // ===== 8. 渐变背景 =====
        sectionTitle("特效")
        themeToggle("渐变背景", "顶部主色渐变到底部", app.prefs.themeGradient) { checked ->
            app.prefs.themeGradient = checked; recreate()
        }

        // ===== 9. 背景模糊 =====
        themeToggle("背景模糊", "半透明毛玻璃效果（API 31+）", app.prefs.themeBlur) { checked ->
            app.prefs.themeBlur = checked; recreate()
        }

        // ===== 10. 动画开关 =====
        themeToggle("列表动画", "短信列表滑动动画", app.prefs.themeAnimation) { checked ->
            app.prefs.themeAnimation = checked; recreate()
        }

        // ===== 11. 字体 =====
        sectionTitle("字体")
        val fontOpts = listOf(
            "default" to "系统默认",
            "sans" to "无衬线",
            "serif" to "衬线",
            "monospace" to "等宽",
            "zh_cn" to "中文字体",
            "custom" to "自定义TTF/OTF",
        )
        val fontRow = LinearLayout(this@HomeActivity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }
        for ((value, label) in fontOpts) {
            val isSelected = app.prefs.themeTypeface == value
            val btn = Button(this@HomeActivity).apply {
                text = label; textSize = 11f
                setTextColor(getColorCompat(if (isSelected) R.color.white else R.color.text_primary))
                setBackgroundResource(if (isSelected) R.drawable.tab_active_bg else R.drawable.bg_card)
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { marginEnd = 4 }
                setOnClickListener {
                    if (value == "custom") {
                        pickFontFile()
                    } else {
                        app.prefs.themeTypeface = value; recreate()
                    }
                }
            }
            fontRow.addView(btn)
        }
        layout.addView(fontRow)
        if (app.prefs.themeTypeface == "custom" && app.prefs.themeFontPath.isNotEmpty()) {
            layout.addView(TextView(this@HomeActivity).apply {
                text = "自定义字体: ${app.prefs.themeFontPath.split("/").lastOrNull()}"
                textSize = 12f; setTextColor(getColorCompat(R.color.text_hint))
                layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = 4 }
            })
        }

        // ===== 12. 服务端同步 =====
        sectionTitle("同步")
        themeToggle("同步服务端主题", "从服务器 /api/theme 获取主题设置覆盖本地", app.prefs.themeSyncServer) { checked ->
            app.prefs.themeSyncServer = checked; if (checked) syncServerTheme()
        }

        // ===== 13. 语言 =====
        sectionTitle("语言 / Language")
        val langOpts = listOf("zh" to "简体中文", "zh-tw" to "繁體中文", "en" to "English")
        val langRow = LinearLayout(this@HomeActivity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }
        for ((code, label) in langOpts) {
            val isSelected = app.prefs.language == code
            val btn = Button(this@HomeActivity).apply {
                text = label; textSize = 12f
                setTextColor(getColorCompat(if (isSelected) R.color.white else R.color.text_primary))
                setBackgroundResource(if (isSelected) R.drawable.tab_active_bg else R.drawable.bg_card)
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { marginEnd = 4 }
                setOnClickListener { app.prefs.language = code; recreate() }
            }
            langRow.addView(btn)
        }
        layout.addView(langRow)
        layout.addView(TextView(this@HomeActivity).apply {
            text = "更改语言后应用将重新创建"
            textSize = 11f; setTextColor(getColorCompat(R.color.text_hint))
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = 2 }
        })

        scroll.addView(layout)
        AlertDialog.Builder(this)
            .setTitle("主题设置")
            .setView(scroll)
            .setNegativeButton("关闭", null)
            .show()
    }

    private fun syncServerTheme() {
        executor.submit {
            try {
                val result = ApiClient.get("/api/theme", app.prefs.sessionId)
                if (result.optBoolean("success", false)) {
                    val d = result.optJSONObject("data") ?: return@submit
                    handler.post {
                        var changed = false
                        if (d.has("dark")) { val v = d.optBoolean("dark"); if (v != app.prefs.themeDark) { app.prefs.themeDark = v; changed = true } }
                        if (d.has("color")) { val v = d.optString("color"); if (v.isNotEmpty() && v != app.prefs.themeColor) { app.prefs.themeColor = v; changed = true } }
                        if (d.has("radius")) { val v = d.optInt("radius"); if (v != app.prefs.themeRadius) { app.prefs.themeRadius = v; changed = true } }
                        if (d.has("fontSize")) { val v = d.optInt("fontSize"); if (v != app.prefs.themeFontSize) { app.prefs.themeFontSize = v; changed = true } }
                        if (d.has("shadow")) { val v = d.optInt("shadow"); if (v != app.prefs.themeShadow) { app.prefs.themeShadow = v; changed = true } }
                        if (d.has("density")) { val v = d.optString("density"); if (v.isNotEmpty() && v != app.prefs.themeDensity) { app.prefs.themeDensity = v; changed = true } }
                        if (d.has("gradient")) { val v = d.optBoolean("gradient"); if (v != app.prefs.themeGradient) { app.prefs.themeGradient = v; changed = true } }
                        if (d.has("animation")) { val v = d.optBoolean("animation"); if (v != app.prefs.themeAnimation) { app.prefs.themeAnimation = v; changed = true } }
                        if (changed) {
                            Toast.makeText(this@HomeActivity, "已同步服务端主题设置", Toast.LENGTH_SHORT).show()
                            recreate()
                        }
                    }
                }
            } catch (_: Exception) {}
        }
    }

    private fun pickFontFile() {
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
            putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("font/ttf", "font/otf", "application/x-font-ttf", "application/x-font-otf"))
        }
        try {
            pickFontLauncher.launch(intent)
        } catch (_: Exception) {
            val fallback = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = "*/*"
            }
            pickFontLauncher.launch(fallback)
        }
    }

    private fun handleFontPicked(uri: android.net.Uri) {
        try {
            val path = uri.path ?: ""
            val inputStream = contentResolver.openInputStream(uri)
            if (inputStream != null) {
                val fontsDir = java.io.File(filesDir, "fonts")
                fontsDir.mkdirs()
                val fileName = "custom_font" + (path.substringAfterLast(".").let { if (it.length <= 4) ".$it" else ".ttf" })
                val outFile = java.io.File(fontsDir, fileName)
                inputStream.use { inp ->
                    outFile.outputStream().use { outp ->
                        inp.copyTo(outp)
                    }
                }
                app.prefs.themeFontPath = outFile.absolutePath
                app.prefs.themeTypeface = "custom"
                Toast.makeText(this, "字体已加载: $fileName", Toast.LENGTH_SHORT).show()
                recreate()
            }
        } catch (e: Exception) {
            Toast.makeText(this, "加载字体失败: ${e.message}", Toast.LENGTH_SHORT).show()
        }
    }

    private fun showAboutDialog() {
        AlertDialog.Builder(this)
            .setTitle("关于")
            .setMessage("短信转网页 v1.0\n\n将手机收到的短信实时转发到网页端，支持多用户、历史记录查看。\n\n帮助:\n- 历史: 查看所有短信记录\n- 已读: 查看已读短信\n- 未读: 查看未读短信\n- 点击短信看详情\n- 长按弹出操作菜单\n- 设置中可搜索/导出\n\n开源地址:\nGitHub: https://github.com/Li-Zhangye/stw\nGitee: https://gitee.com/li-zhangye/stw")
            .setPositiveButton("确定", null)
            .show()
    }

    // ----- Adapter -----

    private inner class SmsAdapter : BaseAdapter() {
        private var items: List<JSONObject> = emptyList()

        fun update(newItems: List<JSONObject>) {
            items = newItems
            notifyDataSetChanged()
        }

        override fun getCount() = items.size
        override fun getItem(pos: Int) = items[pos]
        override fun getItemId(pos: Int) = items[pos].optInt("id").toLong()

        override fun getView(pos: Int, convertView: View?, parent: ViewGroup?): View {
            val p = app.prefs
            val msg = items[pos]
            val isUnread = msg.optInt("is_read") == 0
            val density = p.themeDensity
            val padH = when (density) { "compact" -> 10; "comfortable" -> 22; else -> 16 }
            val padV = when (density) { "compact" -> 8; "comfortable" -> 20; else -> 14 }
            val marginB = when (density) { "compact" -> 4; "comfortable" -> 14; else -> 8 }

            val cardColor: Int
            if (p.themeCardBg.isNotEmpty()) {
                cardColor = try { android.graphics.Color.parseColor(p.themeCardBg) } catch (_: Exception) { 0 }
            } else {
                cardColor = if (p.themeDark) android.graphics.Color.parseColor("#232340") else android.graphics.Color.WHITE
            }

            val primaryColor = if (p.themeTextPrimary.isNotEmpty()) {
                try { android.graphics.Color.parseColor(p.themeTextPrimary) } catch (_: Exception) { getColorCompat(R.color.text_primary) }
            } else getColorCompat(R.color.text_primary)

            val secondaryColor = if (p.themeTextSecondary.isNotEmpty()) {
                try { android.graphics.Color.parseColor(p.themeTextSecondary) } catch (_: Exception) { getColorCompat(R.color.text_secondary) }
            } else getColorCompat(R.color.text_secondary)

            val typeface = when (p.themeTypeface) {
                "monospace" -> android.graphics.Typeface.MONOSPACE
                "serif" -> android.graphics.Typeface.SERIF
                "sans" -> android.graphics.Typeface.SANS_SERIF
                "zh_cn" -> android.graphics.Typeface.DEFAULT
                "custom" -> {
                    val fp = p.themeFontPath
                    if (fp.isNotEmpty()) {
                        try { android.graphics.Typeface.createFromFile(fp) } catch (_: Exception) { android.graphics.Typeface.DEFAULT }
                    } else android.graphics.Typeface.DEFAULT
                }
                else -> android.graphics.Typeface.DEFAULT
            }

            val radius = p.themeRadius.toFloat()
            val elevation = if (isUnread) p.themeShadow.toFloat() + 1f else p.themeShadow.toFloat().coerceAtLeast(0.5f)

            val card = object : LinearLayout(this@HomeActivity) {
                override fun dispatchDraw(canvas: android.graphics.Canvas) {
                    val clip = android.graphics.Path().apply {
                        addRoundRect(0f, 0f, width.toFloat(), height.toFloat(), radius, radius, android.graphics.Path.Direction.CW)
                    }
                    canvas.clipPath(clip)
                    super.dispatchDraw(canvas)
                }
            }.apply {
                orientation = LinearLayout.VERTICAL
                setPadding(padH, padV, padH, padV)
                setBackgroundColor(cardColor)
                layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                    setMargins(0, 0, 0, marginB)
                }
                this.elevation = elevation
            }

            val header = LinearLayout(this@HomeActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                gravity = Gravity.CENTER_VERTICAL
            }

            val dot = View(this@HomeActivity).apply {
                setBackgroundResource(R.drawable.dot_unread)
                layoutParams = ViewGroup.LayoutParams(8, 8)
                visibility = if (isUnread) View.VISIBLE else View.GONE
            }
            val senderTv = TextView(this@HomeActivity).apply {
                text = msg.optString("sender", "")
                textSize = p.themeFontSize.toFloat()
                setTypeface(typeface, if (isUnread) android.graphics.Typeface.BOLD else android.graphics.Typeface.NORMAL)
                setTextColor(if (isUnread) primaryColor else secondaryColor)
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { leftMargin = if (isUnread) 8 else 0 }
            }
            val timeTv = TextView(this@HomeActivity).apply {
                val raw = msg.optString("received_at", "")
                text = if (raw.length > 16) raw.substring(0, 16) else raw
                textSize = (p.themeFontSize - 3).toFloat().coerceAtLeast(10f)
                setTextColor(secondaryColor)
            }
            header.addView(dot)
            header.addView(senderTv)
            header.addView(timeTv)

            val contentTv = TextView(this@HomeActivity).apply {
                text = msg.optString("content", "")
                textSize = (p.themeFontSize - 1).toFloat().coerceAtLeast(12f)
                setTextColor(if (isUnread) primaryColor else secondaryColor)
                setTypeface(typeface, if (isUnread) android.graphics.Typeface.BOLD else android.graphics.Typeface.NORMAL)
                layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = 6 }
                maxLines = 3
                ellipsize = android.text.TextUtils.TruncateAt.END
            }
            card.addView(header)
            card.addView(contentTv)
            return card
        }
    }
}
