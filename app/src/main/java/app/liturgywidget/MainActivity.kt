package app.liturgywidget

import android.app.Activity
import android.os.Bundle
import android.widget.ScrollView
import android.widget.TextView

class MainActivity : Activity() {
    private lateinit var body: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        body = TextView(this)
        body.textSize = 16f
        val pad = (20 * resources.displayMetrics.density).toInt()
        body.setPadding(pad, pad, pad, pad)
        val scroll = ScrollView(this)
        scroll.addView(body)
        setContentView(scroll)
        show()
        val app = applicationContext
        Thread {
            if (Liturgy.refreshIfStale(app)) {
                LiturgyWidget.updateAll(app)
                runOnUiThread { show() }
            }
        }.start()
    }

    private fun show() {
        body.text = Liturgy.fullText(this) +
            "\n\nTo add the widget: long-press the home screen, tap Widgets, and find Liturgical Day."
    }
}
