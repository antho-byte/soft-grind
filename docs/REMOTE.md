**Use the app from your phone or your work laptop, away from home**

The app runs on your home computer. Your phone or laptop only shows the screen. So the home computer has to be **on, awake, with the black window open**.

**1. Keep the home computer awake**
- Windows: Settings → System → Power → *Screen, sleep & hibernate* → set "When plugged in, put my device to sleep after" to **Never**.
- Laptop: keep it plugged in. Settings → Power → *Lid* → "When I close the lid": **Do nothing**.

**2. Protect the app**
- Above, set an **app password**, then turn on **allow other devices**, and restart the app.

**3. Link your devices with Tailscale (free, private)**
- Install **Tailscale** (tailscale.com/download) on the home computer **and** on your phone or work laptop, and sign in to the same account on each.
- On the home computer, Tailscale shows its address, like `100.x.y.z`. Open `http://100.x.y.z:8501` in the browser of your phone or laptop and enter your password.
- On the work laptop, only use the browser. Do not install the app or paste keys there.

**Is my home computer on?**
Open the Tailscale app on your phone: the home computer is listed as *Connected*, or shows when it was *last seen*.

**Phone messages**
Turn on *phone messages* above and you will hear when a video is ready, even if you are not looking at the app.
