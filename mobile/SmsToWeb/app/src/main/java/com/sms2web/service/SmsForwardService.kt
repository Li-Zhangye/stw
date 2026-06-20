package com.sms2web.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.database.Cursor
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.Telephony
import androidx.core.app.NotificationCompat
import com.sms2web.R
import com.sms2web.api.ApiClient
import com.sms2web.ui.HomeActivity
import com.sms2web.util.FileLogger
import com.sms2web.util.PrefManager
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.ExecutorService

class SmsForwardService : Service() {

    companion object {
        const val CHANNEL_ID = "sms_forward_channel"
        const val NOTIFY_ID = 1001
        const val ACTION_SYNC_HISTORY = "sync_history"
    }

    private val executor = Executors.newCachedThreadPool()
    private lateinit var prefs: PrefManager

    override fun onCreate() {
        super.onCreate()
        FileLogger.i("SmsForwardService", "onCreate")
        prefs = PrefManager(this)
        createNotificationChannel()
        startForeground(NOTIFY_ID, buildNotification("短信转发服务运行中"))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent == null) return START_STICKY

        val action = intent.action
        if (action == ACTION_SYNC_HISTORY) {
            syncHistory()
            return START_STICKY
        }

        val sender = intent.getStringExtra("sender") ?: return START_STICKY
        val content = intent.getStringExtra("content") ?: return START_STICKY
        forwardSms(sender, content)
        return START_STICKY
    }

    override fun onDestroy() {
        super.onDestroy()
        executor.shutdownNow()
        FileLogger.i("SmsForwardService", "onDestroy")
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun syncHistory() {
        executor.submit {
            if (!ensureReady()) return@submit

            val currentAddr = prefs.serverAddress
            if (currentAddr == prefs.historySyncedAddr) {
                FileLogger.i("SmsForwardService", "历史短信已同步过，跳过")
                return@submit
            }

            FileLogger.i("SmsForwardService", "开始同步历史短信")
            try {
                val cursor: Cursor? = contentResolver.query(
                    Telephony.Sms.Inbox.CONTENT_URI,
                    arrayOf("address", "body", "date"),
                    null, null, "date ASC"
                )
                if (cursor == null) {
                    FileLogger.w("SmsForwardService", "无法读取短信数据库")
                    return@submit
                }

                val messages = JSONArray()
                while (cursor.moveToNext()) {
                    val sender = cursor.getString(0) ?: continue
                    val body = cursor.getString(1) ?: continue
                    val dateMs = cursor.getLong(2)
                    val dateStr = java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.getDefault()).format(java.util.Date(dateMs))
                    messages.put(JSONObject().apply {
                        put("sender", sender)
                        put("content", body)
                        put("received_at", dateStr)
                    })
                }
                cursor.close()

                if (messages.length() == 0) {
                    FileLogger.i("SmsForwardService", "手机中没有历史短信")
                    prefs.historySyncedAddr = currentAddr
                    return@submit
                }

                FileLogger.i("SmsForwardService", "读取到 ${messages.length()} 条历史短信，开始导入")
                val body = JSONObject().apply { put("messages", messages) }
                val result = ApiClient.post("/api/sms/batch-import", body, prefs.sessionId)
                val imported = result.optInt("imported", 0)
                FileLogger.i("SmsForwardService", "导入完成: $imported 条")
                prefs.historySyncedAddr = currentAddr
            } catch (e: Exception) {
                FileLogger.e("SmsForwardService", "历史短信同步异常", e)
            }
        }
    }

    private fun ensureReady(): Boolean {
        if (prefs.sessionId.isEmpty() || prefs.serverAddress.isEmpty()) {
            FileLogger.w("SmsForwardService", "session或服务器地址为空")
            stopSelf()
            return false
        }
        if (ApiClient.baseUrl.isEmpty()) {
            ApiClient.baseUrl = prefs.serverAddress
        }
        return true
    }

    private fun forwardSms(sender: String, content: String) {
        if (!ensureReady()) return

        executor.submit {
            try {
                val body = JSONObject().apply {
                    put("sender", sender)
                    put("content", content)
                }
                val result = ApiClient.post("/api/sms/receive", body, prefs.sessionId)
                Handler(Looper.getMainLooper()).post {
                    if (result.optBoolean("success", false)) {
                        FileLogger.i("SmsForwardService", "转发成功: 来自=$sender")
                        updateNotification("已转发: 来自 $sender")
                    } else {
                        updateNotification("转发失败: ${result.optString("message", "")}")
                    }
                }
            } catch (e: Exception) {
                FileLogger.e("SmsForwardService", "转发异常", e)
                Handler(Looper.getMainLooper()).post { updateNotification("转发失败: ${e.message}") }
            }
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "短信转发服务",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "用于实时转发短信到服务器"
                setShowBadge(false)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
            FileLogger.i("SmsForwardService", "通知渠道已创建")
        }
    }

    private fun buildNotification(text: String): android.app.Notification {
        val pendingIntent = PendingIntent.getActivity(
            this, 0,
            Intent(this, HomeActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("短信转网页")
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setSilent(true)
            .build()
    }

    private fun updateNotification(text: String) {
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFY_ID, buildNotification(text))
    }
}
