package com.sms2web.ui

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.sms2web.R
import com.sms2web.SmsToWebApp
import com.sms2web.api.ApiClient
import com.sms2web.util.DynamicCodeManager
import com.sms2web.util.FileLogger
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.ExecutorService

class LoginActivity : AppCompatActivity() {
    private val executor = Executors.newCachedThreadPool()
    private lateinit var app: SmsToWebApp
    private var dynamicCodeMgr: DynamicCodeManager? = null
    private var failCount = 0
    private var emailCodeSent = false
    private var isMobile = true

    private lateinit var phoneInput: EditText
    private lateinit var passwordInput: EditText
    private lateinit var loginBtn: Button
    private lateinit var goRegister: TextView
    private lateinit var sendEmailCodeBtn: Button
    private lateinit var dynamicCodeLayout: LinearLayout
    private lateinit var emailCodeLayout: LinearLayout
    private lateinit var dynamicCodeInput: EditText
    private lateinit var emailCodeInput: EditText
    private lateinit var dynamicCodeDisplay: TextView
    private lateinit var dynamicCodeTimer: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        FileLogger.i("LoginActivity", "onCreate 启动")
        setContentView(R.layout.activity_login)
        app = application as SmsToWebApp
        FileLogger.i("LoginActivity", "application 获取完成")

        phoneInput = findViewById(R.id.phoneInput)
        passwordInput = findViewById(R.id.passwordInput)
        loginBtn = findViewById(R.id.loginBtn)
        goRegister = findViewById(R.id.goRegister)
        sendEmailCodeBtn = findViewById(R.id.sendEmailCodeBtn)
        dynamicCodeLayout = findViewById(R.id.dynamicCodeLayout)
        emailCodeLayout = findViewById(R.id.emailCodeLayout)
        dynamicCodeInput = findViewById(R.id.dynamicCodeInput)
        emailCodeInput = findViewById(R.id.emailCodeInput)
        dynamicCodeDisplay = findViewById(R.id.dynamicCodeDisplay)
        dynamicCodeTimer = findViewById(R.id.dynamicCodeTimer)
        FileLogger.i("LoginActivity", "findViewById 初始化完成")

        val savedPhone = app.prefs.lastPhone
        if (savedPhone.isNotEmpty()) {
            phoneInput.setText(savedPhone)
        }

        findViewById<ImageButton>(R.id.settingsBtn).setOnClickListener { showChangeServerDialog() }
        loginBtn.setOnClickListener { doLogin() }
        goRegister.setOnClickListener {
            FileLogger.i("LoginActivity", "用户点击 去注册")
            startActivity(Intent(this, RegisterActivity::class.java))
            finish()
        }
        sendEmailCodeBtn.setOnClickListener { sendEmailCode() }
    }

    override fun onDestroy() {
        super.onDestroy()
        dynamicCodeMgr?.stop()
        executor.shutdownNow()
        FileLogger.i("LoginActivity", "onDestroy")
    }

    private fun doLogin() {
        val phone = phoneInput.text.toString().trim()
        val password = passwordInput.text.toString()
        val emailCode = emailCodeInput.text.toString().trim()
        FileLogger.i("LoginActivity", "用户尝试登录 phone=$phone")

        if (phone.isEmpty() || password.isEmpty()) {
            Toast.makeText(this, "请输入手机号和密码", Toast.LENGTH_SHORT).show()
            return
        }

        if (emailCodeLayout.visibility == View.VISIBLE) {
            if (emailCode.isNotEmpty()) {
                doEmailCodeLogin(phone, emailCode)
            } else {
                Toast.makeText(this, "请输入邮箱验证码", Toast.LENGTH_SHORT).show()
            }
            return
        }

        loginBtn.isEnabled = false
        loginBtn.text = "登录中…"

        executor.submit {
            try {
                val body = JSONObject().apply {
                    put("phone", phone)
                    put("password", password)
                }

                val dynamicInput = dynamicCodeInput.text.toString().trim()
                if (dynamicInput.isNotEmpty()) {
                    body.put("dynamicCode", dynamicInput)
                }

                val result = ApiClient.post("/api/auth/login", body, app.prefs.sessionId)
                Handler(Looper.getMainLooper()).post {
                    loginBtn.isEnabled = true
                    loginBtn.text = "登录"

                    if (result.optBoolean("success", false)) {
                        val cookie = result.optString("_session_cookie", "")
                        if (cookie.isNotEmpty()) {
                            app.prefs.sessionId = cookie
                        }
                        app.prefs.lastPhone = phone
                        FileLogger.i("LoginActivity", "登录成功")
                        Toast.makeText(this, "登录成功", Toast.LENGTH_SHORT).show()
                        startActivity(Intent(this, HomeActivity::class.java))
                        finish()
                    } else {
                        val msg = result.optString("message", "登录失败")
                        FileLogger.w("LoginActivity", "登录失败: $msg")
                        if (result.optBoolean("needDynamicCode", false)) {
                            failCount = result.optInt("failCount", 0)
                            Toast.makeText(this, "密码错误，请输入动态验证码", Toast.LENGTH_SHORT).show()
                            dynamicCodeLayout.visibility = View.VISIBLE
                            startDynamicCode(phone)

                            if (failCount >= 3 && !emailCodeSent) {
                                emailCodeSent = true
                                emailCodeLayout.visibility = View.VISIBLE
                                sendEmailCode()
                            }
                        } else {
                            Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
                        }
                    }
                }
            } catch (e: Exception) {
                FileLogger.e("LoginActivity", "登录请求异常", e)
                Handler(Looper.getMainLooper()).post {
                    loginBtn.isEnabled = true
                    loginBtn.text = "登录"
                    Toast.makeText(this, "网络错误: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun doEmailCodeLogin(phone: String, emailCode: String) {
        FileLogger.i("LoginActivity", "邮箱验证码登录 phone=$phone")
        if (emailCode.isEmpty()) {
            Toast.makeText(this, "请输入邮箱验证码", Toast.LENGTH_SHORT).show()
            return
        }

        loginBtn.isEnabled = false
        loginBtn.text = "验证中…"

        executor.submit {
            try {
                val body = JSONObject().apply {
                    put("phone", phone)
                    put("emailCode", emailCode)
                }
                val result = ApiClient.post("/api/auth/login/verify-email-code", body)
                Handler(Looper.getMainLooper()).post {
                    loginBtn.isEnabled = true
                    loginBtn.text = "登录"

                    if (result.optBoolean("success", false)) {
                        val cookie = result.optString("_session_cookie", "")
                        if (cookie.isNotEmpty()) {
                            app.prefs.sessionId = cookie
                        }
                        app.prefs.lastPhone = phone
                        FileLogger.i("LoginActivity", "邮箱验证码登录成功")
                        Toast.makeText(this, "登录成功", Toast.LENGTH_SHORT).show()
                        startActivity(Intent(this, HomeActivity::class.java))
                        finish()
                    } else {
                        FileLogger.w("LoginActivity", "邮箱验证码登录失败: ${result.optString("message")}")
                        Toast.makeText(this, result.optString("message", "验证失败"), Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                FileLogger.e("LoginActivity", "邮箱验证码请求异常", e)
                Handler(Looper.getMainLooper()).post {
                    loginBtn.isEnabled = true
                    loginBtn.text = "登录"
                    Toast.makeText(this, "网络错误: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun startDynamicCode(phone: String) {
        FileLogger.i("LoginActivity", "启动动态验证码 phone=$phone")
        dynamicCodeMgr?.stop()
        dynamicCodeMgr = DynamicCodeManager(
            phone,
            onCodeRefresh = { code ->
                dynamicCodeDisplay.text = code
            },
            onTimerTick = { sec ->
                dynamicCodeTimer.text = "每10秒自动刷新 · $sec 秒"
                dynamicCodeTimer.setTextColor(
                    if (sec <= 3) ContextCompat.getColor(this@LoginActivity, R.color.error)
                    else ContextCompat.getColor(this@LoginActivity, R.color.text_hint)
                )
            }
        )
        dynamicCodeMgr?.start()
    }

    private fun sendEmailCode() {
        val phone = phoneInput.text.toString().trim()
        if (phone.isEmpty()) return
        FileLogger.i("LoginActivity", "发送邮箱验证码 phone=$phone")

        sendEmailCodeBtn.isEnabled = false
        executor.submit {
            try {
                val body = JSONObject().apply { put("phone", phone) }
                val result = ApiClient.post("/api/auth/login/send-email-code", body)
                Handler(Looper.getMainLooper()).post {
                    sendEmailCodeBtn.isEnabled = true
                    if (result.optBoolean("success", false)) {
                        Toast.makeText(this, "验证码已发送", Toast.LENGTH_SHORT).show()
                    } else {
                        Toast.makeText(this, result.optString("message", "发送失败"), Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                FileLogger.e("LoginActivity", "发送邮箱验证码异常", e)
                Handler(Looper.getMainLooper()).post {
                    sendEmailCodeBtn.isEnabled = true
                    Toast.makeText(this, "网络错误: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun showChangeServerDialog() {
        val input = EditText(this).apply {
            hint = "例：192.168.1.100:3000"
            layoutParams = ViewGroup.MarginLayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(40, 0, 40, 0) }
        }
        AlertDialog.Builder(this)
            .setTitle("更换服务器")
            .setMessage("修改后将断开当前连接，返回首页重新连接新服务器。")
            .setView(input)
            .setPositiveButton("确定") { _, _ ->
                val addr = input.text.toString().trim()
                if (addr.isNotEmpty()) {
                    app.prefs.serverAddress = addr
                    ApiClient.baseUrl = addr
                    Toast.makeText(this, "服务器地址已保存: $addr", Toast.LENGTH_SHORT).show()
                    FileLogger.i("LoginActivity", "用户更换服务器为: $addr")
                    startActivity(Intent(this, MainActivity::class.java))
                    finish()
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }
}
