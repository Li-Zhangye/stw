package com.sms2web.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.Telephony
import com.sms2web.util.FileLogger

class SmsReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        FileLogger.i("SmsReceiver", "收到广播 action=${intent.action}")
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return

        val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent)
        if (messages.isEmpty()) {
            FileLogger.w("SmsReceiver", "短信内容为空")
            return
        }

        val sender = messages[0].displayOriginatingAddress ?: run {
            FileLogger.w("SmsReceiver", "无法获取发件人")
            return
        }
        val content = messages.joinToString("") { it.messageBody ?: "" }
        if (content.isEmpty()) {
            FileLogger.w("SmsReceiver", "短信正文为空")
            return
        }

        FileLogger.i("SmsReceiver", "收到短信: 来自=$sender 内容=$content")

        val serviceIntent = Intent(context, SmsForwardService::class.java).apply {
            putExtra("sender", sender)
            putExtra("content", content)
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(serviceIntent)
        } else {
            context.startService(serviceIntent)
        }
        FileLogger.i("SmsReceiver", "已启动 SmsForwardService")
    }
}
