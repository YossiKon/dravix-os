// Security gallery — browse / download / delete the robot's saved captures, by day.
import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend } from "../api";
import type { SecurityDay, SecurityPhoto } from "../api";
import { toast, toastErr } from "../ui";
import { useI18n } from "../i18n";

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

const timeOf = (p: SecurityPhoto) => (p.ts ? p.ts.slice(11, 19) : p.name.replace(".jpg", ""));

export function SecurityGallery(props: { onChanged?: () => void }) {
  const { tr } = useI18n();
  const [days, setDays] = useState<SecurityDay[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [photos, setPhotos] = useState<SecurityPhoto[]>([]);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    apiGet<{ days: SecurityDay[] }>("/api/security/days")
      .then((r) => setDays(r.days))
      .catch(() => undefined);
    props.onChanged?.();
  }, [props]);

  useEffect(() => refresh(), [refresh]);

  async function openDay(day: string) {
    if (open === day) {
      setOpen(null);
      return;
    }
    setOpen(day);
    try {
      const r = await apiGet<{ photos: SecurityPhoto[] }>(`/api/security/photos?day=${day}&limit=500`);
      setPhotos(r.photos);
    } catch (e) {
      toastErr(e);
    }
  }

  async function delPhoto(p: SecurityPhoto) {
    try {
      await apiSend(`/api/security/photo/${p.day}/${p.name}`, "DELETE");
      setPhotos((cur) => cur.filter((x) => !(x.day === p.day && x.name === p.name)));
      refresh();
    } catch (e) {
      toastErr(e);
    }
  }

  async function delDay(day: string) {
    if (!confirm(tr(`למחוק את כל התמונות מ-${day}?`, `Delete all captures from ${day}?`))) return;
    try {
      await apiSend(`/api/security/day/${day}`, "DELETE");
      if (open === day) setOpen(null);
      refresh();
    } catch (e) {
      toastErr(e);
    }
  }

  async function clearAll() {
    if (!confirm(tr("למחוק את כל צילומי האבטחה?", "Delete ALL security captures?"))) return;
    try {
      await apiSend("/api/security/photos", "DELETE");
      setOpen(null);
      refresh();
    } catch (e) {
      toastErr(e);
    }
  }

  async function makeVideo(day: string) {
    setBusy(true);
    try {
      await apiSend(`/api/security/day/${day}/video`, "POST", {});
      toast(tr("🎬 סרטון טיים-לאפס נוצר", "🎬 Timelapse video built"));
      refresh();
    } catch (e) {
      toastErr(e);
    } finally {
      setBusy(false);
    }
  }

  if (days.length === 0) {
    return <p className="text-sm text-mute">{tr("אין עדיין צילומים שמורים.", "No saved captures yet.")}</p>;
  }

  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <button className="chip" onClick={() => void clearAll()}>
          {tr("🗑 מחק הכל", "🗑 Clear all")}
        </button>
      </div>
      {days.map((d) => (
        <div key={d.day} className="rounded-2xl border border-line bg-card2 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <button className="chip" onClick={() => void openDay(d.day)}>
              {open === d.day ? "▾" : "▸"} <span dir="ltr" className="font-mono">{d.day}</span>
            </button>
            <span className="text-xs text-mute">
              {d.count} {tr("תמונות", "shots")} · {fmtBytes(d.bytes)}
            </span>
            <div className="ms-auto flex items-center gap-2">
              <a className="chip" href={`/api/security/day/${d.day}/zip`}>
                {tr("⬇ ZIP", "⬇ ZIP")}
              </a>
              {d.has_video ? (
                <a className="chip" href={`/api/security/day/${d.day}/video?download=1`}>
                  {tr("🎬 סרטון", "🎬 Video")}
                </a>
              ) : (
                <button className="chip" disabled={busy} onClick={() => void makeVideo(d.day)}>
                  {tr("🎬 צור סרטון", "🎬 Make video")}
                </button>
              )}
              <button className="chip" onClick={() => void delDay(d.day)}>🗑</button>
            </div>
          </div>
          {open === d.day && (
            <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-4">
              {photos.map((p) => (
                <div key={p.name} className="overflow-hidden rounded-xl border border-line bg-black">
                  <a href={`/api/security/photo/${p.day}/${p.name}`} target="_blank" rel="noreferrer">
                    <img
                      src={`/api/security/photo/${p.day}/${p.name}`}
                      alt={timeOf(p)}
                      loading="lazy"
                      className="h-20 w-full object-cover"
                    />
                  </a>
                  <div className="flex items-center justify-between px-1.5 py-1">
                    <span dir="ltr" className="font-mono text-[10px] text-mute">{timeOf(p)}</span>
                    <span className="flex gap-1">
                      <a
                        className="text-xs"
                        href={`/api/security/photo/${p.day}/${p.name}?download=1`}
                        title={tr("הורד", "Download")}
                      >
                        ⬇
                      </a>
                      <button className="text-xs" onClick={() => void delPhoto(p)} title={tr("מחק", "Delete")}>
                        🗑
                      </button>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
