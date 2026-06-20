package com.sms2web.ui

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.sms2web.R
import com.sms2web.api.ApiClient
import com.sms2web.util.FileLogger
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.ExecutorService

class SetPasswordActivity : AppCompatActivity() {
    private val executor = Executors.newCachedThreadPool()
    private lateinit var passwordInput: EditText
    private lateinit var confirmInput: EditText
    private lateinit var completeBtn: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        FileLogger.i("SetPasswordActivity", "onCreate 启动")
        setContentView(R.layout.activity_set_password)

        passwordInput = findViewById(R.id.passwordInput)
        confirmInput = findViewById(R.id.confirmInput)
        completeBtn = findViewById(R.id.completeBtn)
        FileLogger.i("SetPasswordActivity", "findViewById 初始化完成")

        val phone = intent.getStringExtra("phone") ?: ""
        val tempToken = intent.getStringExtra("tempToken") ?: ""
        FileLogger.i("SetPasswordActivity", "接收参数 phone=$phone tempToken=${tempToken.take(8)}...")

        completeBtn.setOnClickListener {
            if (tempToken.isEmpty()) {
                FileLogger.w("SetPasswordActivity", "tempToken 为空，无法完成注册")
                Toast.makeText(this, "验证尚未通过，请返回重新验证", Toast.LENGTH_LONG).show()
                return@setOnClickListener
            }
            val password = passwordInput.text.toString()
            val confirm = confirmInput.text.toString()
            FileLogger.i("SetPasswordActivity", "用户点击完成注册")

            if (password.isEmpty()) {
                Toast.makeText(this, "请输入密码", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            if (password != confirm) {
                Toast.makeText(this, "两次输入的密码不一致", Toast.LENGTH_SHORT).show()
                FileLogger.w("SetPasswordActivity", "两次密码不一致")
                return@setOnClickListener
            }

            val hasDigit = password.any { it.isDigit() }
            val hasLower = password.any { it.isLowerCase() }
            val hasUpper = password.any { it.isUpperCase() }
            val hasSpecial = password.any { "!@#\$%^&*()_+-=[]{}|;':\",.<>?/~`".contains(it) }
            val lengthOk = password.length in 8..32

            if (!(hasDigit && hasLower && hasUpper && hasSpecial && lengthOk)) {
                Toast.makeText(this, "密码必须包含数字、大小写字母、特殊符号，长度8-32位", Toast.LENGTH_LONG).show()
                FileLogger.w("SetPasswordActivity", "密码不符合规则")
                return@setOnClickListener
            }

            completeBtn.isEnabled = false
            completeBtn.text = "注册中…"

            executor.submit {
                try {
                    val body = JSONObject().apply {
                        put("phone", phone)
                        put("password", password)
                        put("tempToken", tempToken)
                    }
                    val result = ApiClient.post("/api/auth/register/set-password", body)
                    Handler(Looper.getMainLooper()).post {
                        completeBtn.isEnabled = true
                        completeBtn.text = "完成注册"

                        if (result.optBoolean("success", false)) {
                            FileLogger.i("SetPasswordActivity", "注册成功")
                            Toast.makeText(this, "注册成功", Toast.LENGTH_SHORT).show()
                            startActivity(Intent(this, LoginActivity::class.java))
                            finish()
                        } else {
                            FileLogger.w("SetPasswordActivity", "注册失败: ${result.optString("message")}")
                            Toast.makeText(this, result.optString("message", "注册失败"), Toast.LENGTH_SHORT).show()
                        }
                    }
                } catch (e: Exception) {
                    FileLogger.e("SetPasswordActivity", "注册请求异常", e)
                    Handler(Looper.getMainLooper()).post {
                        completeBtn.isEnabled = true
                        completeBtn.text = "完成注册"
                        Toast.makeText(this, "网络错误: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        executor.shutdownNow()
        FileLogger.i("SetPasswordActivity", "onDestroy")
    }
}
