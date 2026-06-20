package com.sms2web.ui

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.sms2web.R
import com.sms2web.api.ApiClient
import com.sms2web.util.FileLogger
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.ExecutorService

class VerifyActivity : AppCompatActivity() {
    private val executor = Executors.newCachedThreadPool()
    private lateinit var phoneInput: EditText
    private lateinit var codeInput: EditText
    private lateinit var verifyBtn: Button
    private lateinit var goRegister: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        FileLogger.i("VerifyActivity", "onCreate 启动")
        setContentView(R.layout.activity_verify)

        phoneInput = findViewById(R.id.phoneInput)
        codeInput = findViewById(R.id.codeInput)
        verifyBtn = findViewById(R.id.verifyBtn)
        goRegister = findViewById(R.id.goRegister)
        FileLogger.i("VerifyActivity", "findViewById 初始化完成")

        val key = intent.getStringExtra("key") ?: ""
        val phone = intent.getStringExtra("phone") ?: ""
        FileLogger.i("VerifyActivity", "接收参数 phone=$phone key 长度=${key.length}")

        phoneInput.setText(phone)

        verifyBtn.setOnClickListener {
            val inputPhone = phoneInput.text.toString().trim()
            val code = codeInput.text.toString().trim()
            FileLogger.i("VerifyActivity", "用户点击验证 phone=$inputPhone code=$code")

            if (inputPhone.isEmpty() || code.isEmpty()) {
                Toast.makeText(this, "请填写手机号和验证码", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            if (code.length != 6) {
                Toast.makeText(this, "验证码为6位数字", Toast.LENGTH_SHORT).show()
                FileLogger.w("VerifyActivity", "验证码长度错误: ${code.length}")
                return@setOnClickListener
            }

            verifyBtn.isEnabled = false
            verifyBtn.text = "验证中…"

            executor.submit {
                try {
                    val body = JSONObject().apply {
                        put("key", key)
                        put("phone", inputPhone)
                        put("code", code)
                    }
                    val result = ApiClient.post("/api/auth/register/verify-code", body)
                    Handler(Looper.getMainLooper()).post {
                        verifyBtn.isEnabled = true
                        verifyBtn.text = "下一步"

                        if (result.optBoolean("success", false)) {
                            FileLogger.i("VerifyActivity", "验证码正确")
                            Toast.makeText(this, "验证码正确", Toast.LENGTH_SHORT).show()
                            val tempToken = result.optString("tempToken", "")
                            startActivity(
                                Intent(this, SetPasswordActivity::class.java).putExtra("phone", inputPhone).putExtra("tempToken", tempToken)
                            )
                        } else {
                            FileLogger.w("VerifyActivity", "验证失败: ${result.optString("message")}")
                            Toast.makeText(this, result.optString("message", "验证失败"), Toast.LENGTH_SHORT).show()
                        }
                    }
                } catch (e: Exception) {
                    FileLogger.e("VerifyActivity", "验证请求异常", e)
                    Handler(Looper.getMainLooper()).post {
                        verifyBtn.isEnabled = true
                        verifyBtn.text = "下一步"
                        Toast.makeText(this, "网络错误: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            }
        }

        goRegister.setOnClickListener {
            FileLogger.i("VerifyActivity", "用户点击 重新注册")
            startActivity(Intent(this, RegisterActivity::class.java))
            finish()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        executor.shutdownNow()
        FileLogger.i("VerifyActivity", "onDestroy")
    }
}
