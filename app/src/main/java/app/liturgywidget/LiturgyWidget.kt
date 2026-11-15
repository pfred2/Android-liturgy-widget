package app.liturgywidget

import android.app.AlarmManager
import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import java.util.Calendar

class LiturgyWidget : AppWidgetProvider() {

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        render(context, appWidgetManager, appWidgetIds)
        scheduleNextDay(context)
        // Fetch fresh data in the background (at most once a day), then redraw.
        val pending = goAsync()
        val app = context.applicationContext
        Thread {
            try {
                if (Liturgy.refreshIfStale(app)) updateAll(app)
            } finally {
                pending.finish()
            }
        }.start()
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        if (intent.action == ACTION_NEW_DAY || intent.action == Intent.ACTION_BOOT_COMPLETED) {
            updateAll(context)
            scheduleNextDay(context)
        }
    }

    companion object {
        const val ACTION_NEW_DAY = "app.liturgywidget.NEW_DAY"

        fun updateAll(context: Context) {
            val manager = AppWidgetManager.getInstance(context)
            val ids = manager.getAppWidgetIds(ComponentName(context, LiturgyWidget::class.java))
            if (ids.isNotEmpty()) render(context, manager, ids)
        }

        private fun render(context: Context, manager: AppWidgetManager, ids: IntArray) {
            val d = Liturgy.dayText(context)
            val open = PendingIntent.getActivity(
                context, 0, Intent(context, MainActivity::class.java),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            for (id in ids) {
                val v = RemoteViews(context.packageName, R.layout.widget)
                v.setTextViewText(R.id.date, d.date)
                v.setTextViewText(R.id.trad_name, d.tradName)
                v.setTextViewText(R.id.trad_rank, d.tradRank)
                v.setTextViewText(R.id.trad_reads, d.tradReads)
                v.setTextViewText(R.id.mod_name, d.modName)
                v.setTextViewText(R.id.mod_rank, d.modRank)
                v.setTextViewText(R.id.mod_reads, d.modReads)
                v.setOnClickPendingIntent(R.id.root, open)
                manager.updateAppWidget(id, v)
            }
        }

        /** An inexact alarm shortly after midnight, so the widget changes over on the new day. */
        private fun scheduleNextDay(context: Context) {
            val alarms = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
            val cal = Calendar.getInstance()
            cal.add(Calendar.DAY_OF_YEAR, 1)
            cal.set(Calendar.HOUR_OF_DAY, 0)
            cal.set(Calendar.MINUTE, 1)
            cal.set(Calendar.SECOND, 0)
            cal.set(Calendar.MILLISECOND, 0)
            val intent = Intent(context, LiturgyWidget::class.java).setAction(ACTION_NEW_DAY)
            val pi = PendingIntent.getBroadcast(
                context, 0, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            alarms.set(AlarmManager.RTC, cal.timeInMillis, pi)
        }
    }
}
