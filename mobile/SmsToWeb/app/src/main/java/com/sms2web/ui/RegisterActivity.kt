package com.sms2web.ui

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.ImageButton
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import com.sms2web.R
import com.sms2web.SmsToWebApp
import com.sms2web.api.ApiClient
import com.sms2web.util.FileLogger
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.ExecutorService

class RegisterActivity : AppCompatActivity() {
    private val executor = Executors.newCachedThreadPool()
    private lateinit var app: SmsToWebApp
    private lateinit var phoneInput: EditText
    private lateinit var emailInput: EditText
    private lateinit var sendCodeBtn: Button
    private lateinit var goLogin: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        FileLogger.i("RegisterActivity", "onCreate 启动")
        setContentView(R.layout.activity_register)
        app = application as SmsToWebApp

        phoneInput = findViewById(R.id.phoneInput)
        emailInput = findViewById(R.id.emailInput)
        sendCodeBtn = findViewById(R.id.sendCodeBtn)
        goLogin = findViewById(R.id.goLogin)
        FileLogger.i("RegisterActivity", "findViewById 初始化完成")

        findViewById<ImageButton>(R.id.settingsBtn).setOnClickListener { showChangeServerDialog() }
        sendCodeBtn.setOnClickListener { sendCode() }
        goLogin.setOnClickListener {
            FileLogger.i("RegisterActivity", "用户点击 去登录")
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        executor.shutdownNow()
        FileLogger.i("RegisterActivity", "onDestroy")
    }

    private fun sendCode() {
        val phone = phoneInput.text.toString().trim()
        val email = emailInput.text.toString().trim()
        FileLogger.i("RegisterActivity", "用户发送验证码 phone=$phone email=$email")

        if (phone.isEmpty() || email.isEmpty()) {
            Toast.makeText(this, "请输入手机号和邮箱", Toast.LENGTH_SHORT).show()
            return
        }
        if (!phone.matches(Regex("1[3-9]\\d{9}"))) {
            Toast.makeText(this, "手机号格式不正确", Toast.LENGTH_SHORT).show()
            FileLogger.w("RegisterActivity", "手机号格式错误: $phone")
            return
        }
        if (!email.matches(Regex("[^\\s@]+@[^\\s@]+\\.[^\\s@]+"))) {
            Toast.makeText(this, "邮箱格式不正确", Toast.LENGTH_SHORT).show()
            FileLogger.w("RegisterActivity", "邮箱格式错误: $email")
            return
        }

        sendCodeBtn.isEnabled = false
        sendCodeBtn.text = "发送中…"

        executor.submit {
            try {
                val body = JSONObject().apply {
                    put("phone", phone)
                    put("email", email)
                }
                val result = ApiClient.post("/api/auth/register/send-code", body)
                Handler(Looper.getMainLooper()).post {
                    sendCodeBtn.isEnabled = true
                    sendCodeBtn.text = "发送验证码"

                    if (result.optBoolean("success", false)) {
                        FileLogger.i("RegisterActivity", "验证码发送成功")
                        Toast.makeText(this, "验证码已发送", Toast.LENGTH_SHORT).show()
                        val key = result.optString("key", "")
                        startActivity(
                            Intent(this, VerifyActivity::class.java).putExtra("phone", phone).putExtra("key", key)
                        )
                    } else {
                        FileLogger.w("RegisterActivity", "验证码发送失败: ${result.optString("message")}")
                        Toast.makeText(this, result.optString("message", "发送失败"), Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                FileLogger.e("RegisterActivity", "发送验证码异常", e)
                Handler(Looper.getMainLooper()).post {
                    sendCodeBtn.isEnabled = true
                    sendCodeBtn.text = "发送验证码"
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
                    FileLogger.i("RegisterActivity", "用户更换服务器为: $addr")
                    startActivity(Intent(this, MainActivity::class.java))
                    finish()
                }
            }
            .setNegativeButton("取消", null)
            .show()
    }
}
