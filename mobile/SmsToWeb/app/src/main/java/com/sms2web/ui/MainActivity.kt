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
import com.sms2web.SmsToWebApp
import com.sms2web.api.ApiClient
import com.sms2web.util.FileLogger
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Socket
import java.net.URL
import java.util.Collections
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

class MainActivity : AppCompatActivity() {
    private val executor = Executors.newCachedThreadPool()
    private lateinit var serverAddress: EditText
    private lateinit var confirmServerBtn: Button
    private lateinit var app: SmsToWebApp

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        FileLogger.i("MainActivity", "onCreate 启动")
        setContentView(R.layout.activity_main)

        serverAddress = findViewById(R.id.serverAddress)
        confirmServerBtn = findViewById(R.id.confirmServerBtn)
        FileLogger.i("MainActivity", "findViewById 初始化完成")

        app = application as SmsToWebApp
        val saved = app.prefs.serverAddress
        if (saved.isNotEmpty()) {
            val ipOnly = saved.split(":")[0]
            serverAddress.setText(ipOnly)
            FileLogger.i("MainActivity", "已保存的地址: $saved")
        }

        confirmServerBtn.setOnClickListener {
            val raw = serverAddress.text.toString().trim()
            FileLogger.i("MainActivity", "用户点击确认，地址=$raw")
            if (raw.isEmpty()) {
                Toast.makeText(this, "请输入服务器地址", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            // 去掉 http:// 或 https:// 前缀
            var addr = raw
            if (addr.startsWith("http://") || addr.startsWith("https://")) {
                addr = addr.substringAfter("://")
            }
            // 去掉尾部路径（/ 或 /xxx）
            val slashIdx = addr.indexOf('/')
            if (slashIdx >= 0) addr = addr.substring(0, slashIdx)

            if (addr.contains(":")) {
                val parts = addr.split(":")
                if (parts.size < 2 || parts.last().isEmpty()) {
                    Toast.makeText(this, "请输入端口号（格式: IP:端口）", Toast.LENGTH_SHORT).show()
                    return@setOnClickListener
                }
                val ip = parts.dropLast(1).joinToString(":")
                val portStr = parts.last()
                val port = portStr.toIntOrNull()
                if (port == null || port !in 1..65535) {
                    Toast.makeText(this, "端口号格式不正确（1-65535）", Toast.LENGTH_SHORT).show()
                    return@setOnClickListener
                }
                verifyAndConnect(ip, port)
            } else {
                scanAndConnect(addr)
            }
        }
    }

    private fun verifyAndConnect(ip: String, port: Int) {
        confirmServerBtn.isEnabled = false
        confirmServerBtn.text = "检测中…"

        executor.submit {
            // 第一步：TCP 检测端口是否开放
            var tcpOk = false
            try {
                val s = Socket()
                s.connect(InetSocketAddress(ip, port), 2000)
                s.close()
                tcpOk = true
            } catch (e: Exception) {
                FileLogger.e("MainActivity", "TCP端口检测失败: $ip:$port", e)
            }

            if (!tcpOk) {
                Handler(Looper.getMainLooper()).post {
                    confirmServerBtn.isEnabled = true
                    confirmServerBtn.text = "确认"
                    Toast.makeText(this, "端口 $port 未开放，请检查服务器是否运行", Toast.LENGTH_LONG).show()
                }
                return@submit
            }

            // 第二步：HTTP 验证，检查响应体是否匹配 API 格式
            var conn: HttpURLConnection? = null
            try {
                conn = URL("http://$ip:$port/api/sms/list").openConnection() as HttpURLConnection
                conn.connectTimeout = 3000
                conn.readTimeout = 3000
                conn.instanceFollowRedirects = false

                if (conn.responseCode != 200) {
                    Handler(Looper.getMainLooper()).post {
                        confirmServerBtn.isEnabled = true
                        confirmServerBtn.text = "确认"
                        Toast.makeText(this, "端口 $port 无响应（HTTP ${conn.responseCode}）", Toast.LENGTH_LONG).show()
                    }
                    return@submit
                }

                val body = conn.inputStream.bufferedReader().readText()
                val json = org.json.JSONObject(body)
                val ok = json.has("success") || json.has("code") || json.has("sms_list")

                if (!ok) {
                    Handler(Looper.getMainLooper()).post {
                        confirmServerBtn.isEnabled = true
                        confirmServerBtn.text = "确认"
                        Toast.makeText(this, "端口 $port 响应异常，非短信转网页服务", Toast.LENGTH_LONG).show()
                    }
                    return@submit
                }

                FileLogger.i("MainActivity", "端口验证通过: $ip:$port")
                Handler(Looper.getMainLooper()).post {
                    confirmServerBtn.isEnabled = true
                    confirmServerBtn.text = "确认"
                    connectToServer("$ip:$port")
                }
            } catch (e: Exception) {
                FileLogger.e("MainActivity", "端口验证异常", e)
                Handler(Looper.getMainLooper()).post {
                    confirmServerBtn.isEnabled = true
                    confirmServerBtn.text = "确认"
                    Toast.makeText(this, "无法连接到 $ip:$port", Toast.LENGTH_LONG).show()
                }
            } finally {
                conn?.disconnect()
            }
        }
    }

    private fun connectToServer(addr: String) {
        ApiClient.baseUrl = addr
        app.prefs.serverAddress = addr

        val session = app.prefs.sessionId
        if (session.isNotEmpty()) {
            FileLogger.i("MainActivity", "有保存的session，尝试自动登录")
            confirmServerBtn.isEnabled = false
            confirmServerBtn.text = "登录中…"
            executor.submit {
                try {
                    val resp = ApiClient.post("/api/auth/user/info", JSONObject(), session)
                    Handler(Looper.getMainLooper()).post {
                        if (isFinishing) return@post
                        confirmServerBtn.isEnabled = true
                        confirmServerBtn.text = "确认"
                        if (resp.optBoolean("success", false)) {
                            FileLogger.i("MainActivity", "自动登录成功，跳转到首页")
                            startActivity(Intent(this, HomeActivity::class.java))
                            finish()
                        } else {
                            FileLogger.i("MainActivity", "自动登录失败，跳转到登录页")
                            startActivity(Intent(this, LoginActivity::class.java))
                            finish()
                        }
                    }
                } catch (e: Exception) {
                    FileLogger.e("MainActivity", "自动登录异常", e)
                    Handler(Looper.getMainLooper()).post {
                        if (isFinishing) return@post
                        confirmServerBtn.isEnabled = true
                        confirmServerBtn.text = "确认"
                        Toast.makeText(this, "连接服务器成功，但登录失败: ${e.message}", Toast.LENGTH_LONG).show()
                    }
                }
            }
        } else {
            FileLogger.i("MainActivity", "跳转到登录页")
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
        }
    }

    private fun scanAndConnect(ip: String) {
        confirmServerBtn.isEnabled = false
        confirmServerBtn.text = "探测中…"

        executor.submit {
            val foundPort = scanServerPort(ip)
            Handler(Looper.getMainLooper()).post {
                if (isFinishing) return@post
                confirmServerBtn.isEnabled = true
                confirmServerBtn.text = "确认"
                if (foundPort != null) {
                    connectToServer("$ip:$foundPort")
                } else {
                    Toast.makeText(this, "未检测到服务端口，请手动输入IP:端口", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun scanServerPort(ip: String): Int? {
        val tcpTimeout = 500
        val httpTimeout = 2000
        val threadCount = 100
        val found = AtomicInteger(-1)

        // 第一轮：TCP 快速扫描所有端口，收集开放端口
        val openPorts = Collections.synchronizedList(mutableListOf<Int>())
        val tcpLatch = CountDownLatch(65535)
        val tcpExecutor = Executors.newFixedThreadPool(threadCount)

        for (port in 1..65535) {
            tcpExecutor.submit {
                try {
                    val s = Socket()
                    s.connect(InetSocketAddress(ip, port), tcpTimeout)
                    s.close()
                    openPorts.add(port)
                } catch (_: Exception) {
                } finally {
                    tcpLatch.countDown()
                }
            }
        }
        tcpLatch.await(30, TimeUnit.SECONDS)
        tcpExecutor.shutdownNow()
        FileLogger.i("MainActivity", "TCP扫描完成，发现 ${openPorts.size} 个开放端口: $openPorts")

        if (openPorts.isEmpty()) return null

        // 第二轮：HTTP 验证开放端口，找服务端口
        val httpLatch = CountDownLatch(1)
        val httpExecutor = Executors.newFixedThreadPool(threadCount)

        for (port in openPorts) {
            if (found.get() > 0) break
            httpExecutor.submit {
                if (found.get() > 0) return@submit
                var conn: HttpURLConnection? = null
                try {
                    conn = URL("http://$ip:$port/api/sms/list").openConnection() as HttpURLConnection
                    conn.connectTimeout = httpTimeout
                    conn.readTimeout = httpTimeout
                    conn.instanceFollowRedirects = false
                    if (conn.responseCode == 200) {
                        found.set(port)
                        FileLogger.i("MainActivity", "自动探测到服务端口 $port")
                        httpLatch.countDown()
                    }
                } catch (_: Exception) {
                } finally {
                    conn?.disconnect()
                }
            }
        }
        httpLatch.await(30, TimeUnit.SECONDS)
        httpExecutor.shutdownNow()

        val p = found.get()
        return if (p > 0) p else null
    }

    override fun onDestroy() {
        super.onDestroy()
        executor.shutdownNow()
        FileLogger.i("MainActivity", "onDestroy")
    }
}
