package com.sms2web.api

import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.ConnectException
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URL
import javax.net.ssl.SSLException

object ApiClient {
    var baseUrl: String = ""
        set(value) { field = value.trimEnd('/') }
    private var preferHttps: Boolean? = null

    private fun buildUrl(path: String, useHttps: Boolean): URL {
        val scheme = if (useHttps) "https://" else "http://"
        val u = if (baseUrl.startsWith("http://") || baseUrl.startsWith("https://"))
            "${scheme}${baseUrl.removePrefix("http://").removePrefix("https://")}$path"
        else
            "$scheme$baseUrl$path"
        return URL(u)
    }

    private fun connect(path: String, body: JSONObject? = null, sessionId: String = ""): JSONObject {
        val host = baseUrl.removePrefix("http://").removePrefix("https://").split(":")[0]
        val isIp = Regex("^\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}$").matches(host)

        val first = when {
            isIp -> false
            preferHttps != null -> preferHttps!!
            else -> true
        }
        val attempts = mutableListOf(first)
        if (preferHttps == null && !isIp) attempts.add(!first)

        for (useHttps in attempts.distinct()) {
            var conn: HttpURLConnection? = null
            try {
                val url = buildUrl(path, useHttps)
                conn = url.openConnection() as HttpURLConnection
                conn.connectTimeout = 5000
                conn.readTimeout = 15000

                if (body != null) {
                    conn.requestMethod = "POST"
                    conn.doOutput = true
                    conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                    conn.setRequestProperty("X-Requested-With", "XMLHttpRequest")
                    if (sessionId.isNotEmpty()) {
                        conn.setRequestProperty("Cookie", "session_id=$sessionId")
                    }
                    OutputStreamWriter(conn.outputStream, "UTF-8").use { writer ->
                        writer.write(body.toString())
                    }
                } else {
                    conn.requestMethod = "GET"
                    conn.setRequestProperty("X-Requested-With", "XMLHttpRequest")
                    if (sessionId.isNotEmpty()) {
                        conn.setRequestProperty("Cookie", "session_id=$sessionId")
                    }
                }

                val code = conn.responseCode
                val cookieHeader = conn.getHeaderField("Set-Cookie")
                val sessionCookie = parseSessionCookie(cookieHeader)

                val inputStream = if (code in 200..299) conn.inputStream
                    else (conn.errorStream ?: conn.inputStream)
                val reader = BufferedReader(InputStreamReader(inputStream, "UTF-8"))
                val response = reader.readText()
                reader.close()

                preferHttps = useHttps
                val json = JSONObject(response)
                if (sessionCookie != null) {
                    json.put("_session_cookie", sessionCookie)
                }
                return json
            } catch (e: SSLException) {
                if (useHttps && preferHttps == null) continue
                throw RuntimeException("SSL连接失败，请检查服务器是否支持HTTPS", e)
            } catch (e: SocketTimeoutException) {
                if (useHttps && preferHttps == null) continue
                throw RuntimeException("连接超时", e)
            } catch (e: ConnectException) {
                if (useHttps && preferHttps == null) continue
                throw RuntimeException("无法连接到服务器", e)
            } catch (e: java.io.IOException) {
                if (useHttps && preferHttps == null) continue
                throw RuntimeException("网络连接失败", e)
            } finally {
                conn?.disconnect()
            }
        }
        throw RuntimeException("无法连接到服务器")
    }

    fun post(path: String, body: JSONObject, sessionId: String = ""): JSONObject {
        return connect(path, body, sessionId)
    }

    fun get(path: String, sessionId: String = ""): JSONObject {
        return connect(path, null, sessionId)
    }

    private fun parseSessionCookie(header: String?): String? {
        if (header == null) return null
        for (part in header.split(";")) {
            val trimmed = part.trim()
            if (trimmed.startsWith("session_id=")) {
                return trimmed.substring(11)
            }
        }
        return null
    }
}
