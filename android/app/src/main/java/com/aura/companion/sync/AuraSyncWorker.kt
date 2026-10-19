package com.aura.companion.sync

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.aura.companion.data.local.AuraDatabase
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Background WorkManager worker that periodically polls AURA backend for
 * pending high-risk tool actions and synchronizes local Room cache.
 */
class AuraSyncWorker(
    appContext: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(appContext, workerParams) {

    private val db = AuraDatabase.getInstance(appContext)

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        try {
            val now = System.currentTimeMillis()
            Log.d("AuraSyncWorker", "Executing scheduled background sync at $now")

            // 1. Purge expired local approvals
            db.approvalDao().purgeExpired(now)

            // 2. In a real environment, query: GET /api/v1/devices/pending-approvals
            // and upsert newly discovered requests to Room DB.
            Result.success()
        } catch (e: Exception) {
            Log.e("AuraSyncWorker", "Background sync failed: ${e.message}", e)
            Result.retry()
        }
    }
}
