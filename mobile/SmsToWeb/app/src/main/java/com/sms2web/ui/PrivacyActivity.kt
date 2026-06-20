package com.sms2web.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.sms2web.R

class PrivacyActivity : AppCompatActivity() {

    companion object {
        private const val PERMISSION_REQUEST_CODE = 100
    }

    private lateinit var agreeBtn: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val app = application as com.sms2web.SmsToWebApp
        if (app.prefs.privacyAgreed) {
            checkAndRequestPermissions()
            return
        }

        setContentView(R.layout.activity_privacy)

        agreeBtn = findViewById(R.id.agreeBtn)

        agreeBtn.setOnClickListener {
            app.prefs.privacyAgreed = true
            checkAndRequestPermissions()
        }
    }

    private fun checkAndRequestPermissions() {
        val needed = mutableListOf<String>()

        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_EXTERNAL_STORAGE)
                != PackageManager.PERMISSION_GRANTED
            ) {
                needed.add(Manifest.permission.WRITE_EXTERNAL_STORAGE)
            }
        }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECEIVE_SMS)
            != PackageManager.PERMISSION_GRANTED
        ) {
            needed.add(Manifest.permission.RECEIVE_SMS)
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_SMS)
            != PackageManager.PERMISSION_GRANTED
        ) {
            needed.add(Manifest.permission.READ_SMS)
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) {
                needed.add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }

        if (needed.isEmpty()) {
            goNext()
            return
        }

        showPermissionRationale(needed.toTypedArray())
    }

    private fun showPermissionRationale(permissions: Array<String>) {
        val message = buildString {
            append("为了正常使用本应用，需要以下权限：\n\n")
            permissions.forEach { perm ->
                when (perm) {
                    Manifest.permission.WRITE_EXTERNAL_STORAGE -> append("• 存储权限：用于保存运行日志\n")
                    Manifest.permission.RECEIVE_SMS -> append("• 接收短信权限：用于接收新短信\n")
                    Manifest.permission.READ_SMS -> append("• 读取短信权限：用于读取短信内容\n")
                    Manifest.permission.POST_NOTIFICATIONS -> append("• 通知权限：用于显示转发状态\n")
                }
            }
            append("\n请点击\u201C允许\u201D授予权限。")
        }

        AlertDialog.Builder(this)
            .setTitle("权限申请")
            .setMessage(message)
            .setCancelable(false)
            .setPositiveButton("去授权") { _, _ ->
                ActivityCompat.requestPermissions(this, permissions, PERMISSION_REQUEST_CODE)
            }
            .setNegativeButton("退出应用") { _, _ -> finish() }
            .show()
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != PERMISSION_REQUEST_CODE) return

        val denied = permissions.filterIndexed { i, _ ->
            grantResults[i] != PackageManager.PERMISSION_GRANTED
        }

        if (denied.isEmpty()) {
            goNext()
        } else {
            Toast.makeText(this, "权限被拒绝，部分功能可能无法使用", Toast.LENGTH_LONG).show()
            goNext()
        }
    }

    private fun goNext() {
        val sessionId = (application as com.sms2web.SmsToWebApp).prefs.sessionId
        if (sessionId.isNotEmpty()) {
            startActivity(Intent(this, HomeActivity::class.java))
        } else {
            startActivity(Intent(this, MainActivity::class.java))
        }
        finish()
    }
}
