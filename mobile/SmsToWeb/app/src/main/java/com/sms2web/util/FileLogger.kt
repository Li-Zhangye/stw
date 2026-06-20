package com.sms2web.util

import android.content.Context
import android.util.Log
import java.io.File
import java.io.FileWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object FileLogger {
    private const val LOG_FILE = "sms2web.log"
    private const val MAX_LOG_SIZE = 5 * 1024 * 1024L

    private val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.getDefault())
    private val lock = Any()
    private var writer: FileWriter? = null

    fun init(context: Context) {
        synchronized(lock) {
            writer = tryOpen(context.filesDir.absolutePath + "/logs")
        }
    }

    private fun tryOpen(dirPath: String): FileWriter? {
        return try {
            val dir = File(dirPath)
            if (!dir.exists()) dir.mkdirs()
            val file = File(dir, LOG_FILE)
            if (file.exists() && file.length() > MAX_LOG_SIZE) {
                val old = File(dir, "sms2web_old.log")
                old.delete()
                if (!file.renameTo(old)) {
                    file.delete()
                }
            }
            FileWriter(file, true).also { writer = it }
        } catch (e: Exception) {
            Log.e("FileLogger", "无法创建日志文件($dirPath)", e)
            null
        }
    }

    private fun write(level: String, tag: String, msg: String) {
        synchronized(lock) {
            val w = writer ?: return
            try {
                val time = dateFormat.format(Date())
                val line = "[$time] [$level] [$tag] $msg\n"
                w.write(line)
                w.flush()
            } catch (e: Exception) {
                Log.e("FileLogger", "写日志失败", e)
            }
        }
    }

    fun i(tag: String, msg: String) {
        Log.i(tag, msg)
        write("INFO", tag, msg)
    }

    fun w(tag: String, msg: String) {
        Log.w(tag, msg)
        write("WARN", tag, msg)
    }

    fun e(tag: String, msg: String, tr: Throwable? = null) {
        Log.e(tag, msg, tr)
        write("ERROR", tag, msg + (tr?.let { "\n  " + Log.getStackTraceString(it) } ?: ""))
    }

    fun close() {
        synchronized(lock) {
            try {
                writer?.close()
            } catch (_: Exception) {}
            writer = null
        }
    }
}
