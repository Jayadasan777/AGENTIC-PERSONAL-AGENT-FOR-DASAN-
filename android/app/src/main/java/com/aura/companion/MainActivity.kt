package com.aura.companion

import android.os.Bundle
import android.widget.Toast
import androidx.activity.compose.setContent
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.lifecycleScope
import com.aura.companion.auth.BiometricAuthManager
import com.aura.companion.data.local.ApprovalEntity
import com.aura.companion.data.local.AuraDatabase
import com.aura.companion.ui.AuraCompanionApp
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

class MainActivity : FragmentActivity() {

    private lateinit var db: AuraDatabase
    private lateinit var biometricManager: BiometricAuthManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        db = AuraDatabase.getInstance(this)
        biometricManager = BiometricAuthManager(this)

        lifecycleScope.launch {
            db.approvalDao().getActiveApprovals(System.currentTimeMillis()).collectLatest { approvals ->
                setContent {
                    AuraCompanionApp(
                        approvals = approvals,
                        onApprove = { item -> handleBiometricApproval(item) },
                        onDeny = { item -> handleDenial(item) }
                    )
                }
            }
        }
    }

    private fun handleBiometricApproval(item: ApprovalEntity) {
        if (!biometricManager.isBiometricAvailable()) {
            Toast.makeText(this, "Biometrics unavailable on device", Toast.LENGTH_SHORT).show()
            return
        }

        biometricManager.promptBiometricApproval(
            title = "AURA Authorization Required",
            subtitle = "Tool: ${item.toolName} (${item.riskLevel})",
            description = "Confirm your biometric identity to approve this agent action.",
            onSuccess = {
                lifecycleScope.launch {
                    db.approvalDao().markResolved(item.approvalToken, "APPROVE")
                    Toast.makeText(this@MainActivity, "Action Approved via Biometrics", Toast.LENGTH_SHORT).show()
                }
            },
            onError = { err ->
                Toast.makeText(this, "Approval failed: $err", Toast.LENGTH_SHORT).show()
            }
        )
    }

    private fun handleDenial(item: ApprovalEntity) {
        lifecycleScope.launch {
            db.approvalDao().markResolved(item.approvalToken, "DENY")
            Toast.makeText(this@MainActivity, "Action Denied", Toast.LENGTH_SHORT).show()
        }
    }
}
