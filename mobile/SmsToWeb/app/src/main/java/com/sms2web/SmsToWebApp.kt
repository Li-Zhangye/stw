package com.sms2web

import android.app.Application
import com.sms2web.util.FileLogger
import com.sms2web.util.PrefManager

class SmsToWebApp : Application() {
    lateinit var prefs: PrefManager
        private set

    override fun onCreate() {
        super.onCreate()
        FileLogger.init(this)
        FileLogger.i("App", "应用启动 onCreate")
        prefs = PrefManager(this)
        FileLogger.i("App", "PrefManager 初始化完成")
    }

    override fun onTerminate() {
        super.onTerminate()
        FileLogger.close()
    }
}
