package com.sms2web.util

import android.os.Handler
import android.os.Looper
import com.sms2web.api.ApiClient
import java.util.concurrent.Executors
import java.util.concurrent.ExecutorService

class DynamicCodeManager(
    private val phone: String,
    private val onCodeRefresh: (String) -> Unit,
    private val onTimerTick: (Int) -> Unit
) {
    private var countdown = 10
    private val handler = Handler(Looper.getMainLooper())
    private val executor = Executors.newCachedThreadPool()
    private var polling = false
    private var stopped = false

    private val pollRunnable = object : Runnable {
        override fun run() {
            if (stopped) return
            fetchCode()
            handler.postDelayed(this, 10000)
        }
    }

    private val countdownRunnable = object : Runnable {
        override fun run() {
            if (stopped) return
            countdown--
            if (countdown <= 0) countdown = 10
            onTimerTick(countdown)
            handler.postDelayed(this, 1000)
        }
    }

    fun start() {
        stopped = false
        countdown = 10
        polling = true
        fetchCode()
        handler.postDelayed(pollRunnable, 10000)
        handler.postDelayed(countdownRunnable, 1000)
    }

    fun stop() {
        stopped = true
        polling = false
        handler.removeCallbacks(pollRunnable)
        handler.removeCallbacks(countdownRunnable)
        executor.shutdownNow()
    }

    private fun fetchCode() {
        executor.submit {
            try {
                val result = ApiClient.get(
                    "/api/dynamic-code?phone=${java.net.URLEncoder.encode(phone, "UTF-8")}"
                )
                val code = result.optString("code", "")
                if (code.isNotEmpty()) {
                    countdown = 10
                    handler.post {
                        onCodeRefresh(code)
                    }
                }
            } catch (e: Exception) {
                FileLogger.e("DynamicCodeManager", "获取动态码异常 phone=$phone", e)
            }
        }
    }
}
