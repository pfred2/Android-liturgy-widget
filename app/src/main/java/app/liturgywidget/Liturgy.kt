package app.liturgywidget

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class DayText(
    val date: String,
    val tradName: String,
    val tradRank: String,
    val tradReads: String,
    val modName: String,
    val modRank: String,
    val modReads: String,
)

object Liturgy {
    private const val DATA_URL =
        "https://raw.githubusercontent.com/pfred2/android-liturgy-widget/main/data/liturgy.json"
    private const val FILE = "liturgy.json"
    private const val MAX_AGE_MS = 24L * 60 * 60 * 1000
    private const val RETRY_MS = 6L * 60 * 60 * 1000
    private val ROMAN = arrayOf("", "I", "II", "III", "IV")

    private fun todayKey(): String = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())

    private fun parse(text: String): JSONObject? =
        try {
            JSONObject(text)
        } catch (e: Exception) {
            null
        }

    /** Prefer the refreshed copy when it covers today, otherwise the copy bundled in the APK. */
    private fun load(ctx: Context, key: String): JSONObject {
        val cached = File(ctx.filesDir, FILE)
        if (cached.exists()) {
            val j = parse(cached.readText())
            if (j != null && j.has(key)) return j
        }
        val bundled = ctx.assets.open(FILE).bufferedReader().use { it.readText() }
        return parse(bundled) ?: JSONObject()
    }

    /** Downloads the data file from the repository at most once a day. Returns true if a new file was saved. */
    fun refreshIfStale(ctx: Context): Boolean {
        val file = File(ctx.filesDir, FILE)
        val now = System.currentTimeMillis()
        if (file.exists() && now - file.lastModified() < MAX_AGE_MS) return false
        val prefs = ctx.getSharedPreferences("liturgy", Context.MODE_PRIVATE)
        if (now - prefs.getLong("lastTry", 0L) < RETRY_MS) return false
        prefs.edit().putLong("lastTry", now).apply()
        return try {
            val conn = URL(DATA_URL).openConnection() as HttpURLConnection
            conn.connectTimeout = 4000
            conn.readTimeout = 6000
            val text = conn.inputStream.bufferedReader().use { it.readText() }
            val json = parse(text)
            if (json == null || json.length() < 100) {
                false
            } else {
                val tmp = File(ctx.filesDir, "$FILE.tmp")
                tmp.writeText(text)
                tmp.renameTo(file)
            }
        } catch (e: Exception) {
            false
        }
    }

    private fun tradShort(ef: JSONObject): Triple<String, String, String> {
        val masses = ef.optJSONArray("masses")
        val m = if (masses != null && masses.length() > 0) masses.getJSONObject(0) else ef
        var rank = "Class " + ROMAN[ef.optInt("rank", 4).coerceIn(1, 4)]
        if (ef.optBoolean("octave")) rank += " · octave day"
        if (masses != null && masses.length() > 1) rank += " · ${masses.length()} Masses (open app)"
        val ep = m.optJSONArray("epistle") ?: JSONArray()
        val lines = ArrayList<String>()
        val shown = minOf(ep.length(), 3)
        for (i in 0 until shown) {
            lines.add((if (ep.length() > 1) "Lesson ${i + 1}" else "Epistle") + ": " + ep.getString(i))
        }
        if (ep.length() > shown) lines.add("+${ep.length() - shown} more lessons")
        lines.add("Gospel: " + m.optString("gospel"))
        return Triple(m.optString("name"), rank, lines.joinToString("\n"))
    }

    private fun modern(of: JSONObject?): Triple<String, String, String> {
        if (of == null) {
            return Triple("Not available yet", "", "The 1969 readings for this date are not in the data source yet.")
        }
        val rd = of.optJSONArray("readings") ?: JSONArray()
        val lines = ArrayList<String>()
        for (i in 0 until rd.length()) {
            val p = rd.getJSONArray(i)
            lines.add(p.getString(0) + ": " + p.getString(1))
        }
        return Triple(of.optString("name"), of.optString("rank"), lines.joinToString("\n"))
    }

    fun dayText(ctx: Context): DayText {
        val key = todayKey()
        val dateText = SimpleDateFormat("EEEE, MMMM d", Locale.getDefault()).format(Date())
        val day = load(ctx, key).optJSONObject(key)
            ?: return DayText(dateText, "No data for today", "", "Open the app to refresh.", "", "", "")
        val t = tradShort(day.getJSONObject("ef"))
        val m = modern(day.optJSONObject("of"))
        return DayText(dateText, t.first, t.second, t.third, m.first, m.second, m.third)
    }

    /** Everything for today: all Masses and all lessons, for the app screen. */
    fun fullText(ctx: Context): String {
        val key = todayKey()
        val day = load(ctx, key).optJSONObject(key)
            ?: return "No data for today. Connect to the internet and reopen the app."
        val ef = day.getJSONObject("ef")
        val sb = StringBuilder()
        sb.append(SimpleDateFormat("EEEE, MMMM d, yyyy", Locale.getDefault()).format(Date())).append("\n\n")
        sb.append("TRADITIONAL · 1962\n")
        val masses = ef.optJSONArray("masses")
        val rank = "Class " + ROMAN[ef.optInt("rank", 4).coerceIn(1, 4)] + if (ef.optBoolean("octave")) " · octave day" else ""
        if (masses != null && masses.length() > 1) {
            sb.append(rank).append("\n")
            for (i in 0 until masses.length()) {
                val m = masses.getJSONObject(i)
                sb.append("\nMass ${i + 1}: ").append(m.optString("name")).append("\n").append(massLines(m))
            }
        } else {
            sb.append(ef.optString("name")).append("\n").append(rank).append("\n").append(massLines(ef))
        }
        sb.append("\n\nMODERN · 1969\n")
        val t = modern(day.optJSONObject("of"))
        sb.append(t.first).append("\n")
        if (t.second.isNotEmpty()) sb.append(t.second).append("\n")
        sb.append(t.third)
        return sb.toString()
    }

    private fun massLines(m: JSONObject): String {
        val ep = m.optJSONArray("epistle") ?: JSONArray()
        val lines = ArrayList<String>()
        for (i in 0 until ep.length()) {
            lines.add((if (ep.length() > 1) "Lesson ${i + 1}" else "Epistle") + ": " + ep.getString(i))
        }
        lines.add("Gospel: " + m.optString("gospel"))
        return lines.joinToString("\n")
    }
}
