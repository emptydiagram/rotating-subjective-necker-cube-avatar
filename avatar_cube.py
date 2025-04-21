from __future__ import annotations
from dotenv import load_dotenv
import os, io, math, datetime as dt
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
from atproto import Client, models

# ─────────────────────────── configuration ───────────────────────────────
START_DATETIME = dt.datetime(2025, 4, 21, 0, 0, 0, tzinfo=dt.timezone.utc)
ZOOM           = 100.0   # px per 2 cube units (smaller than interactive ver.)
CIRCLE_R       = 17      # px
LINE_W         = 6      # px
PITCH_DEG       = 20       # fixed roll
YAW_DEG        = 45      # fixed yaw

# ─────────────────────────── math helpers ────────────────────────────────

def rot_xyz(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Build 3×3 rotation matrix for intrinsic X‑(roll), Y‑(pitch), Z‑(yaw)."""
    cx, cy, cz = np.cos([roll, pitch, yaw])
    sx, sy, sz = np.sin([roll, pitch, yaw])
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx

def project_ortho(P: np.ndarray) -> np.ndarray:
    """Orthographic projection + scaling to screen space (px)."""
    return P[:, :2] * (ZOOM / 2)

# cube geometry (world‑space)
V = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
              [-1, -1,  1], [1, -1,  1], [1, 1,  1], [-1, 1,  1]], dtype=float)
EDGES = [(0, 1), (1, 2), (2, 3), (3, 0),
         (4, 5), (5, 6), (6, 7), (7, 4),
         (0, 4), (1, 5), (2, 6), (3, 7)]

# extent for a fixed frame (covers any rotation)
CUBE_RADIUS_PX = math.sqrt(3) * (ZOOM / 2)
HALF_FRAME     = CUBE_RADIUS_PX + CIRCLE_R + 5

# ─────────────────────────── rendering core ──────────────────────────────

def render_frame(roll_deg: float) -> bytes:
    """Return PNG bytes of cube at given pitch (deg)."""
    # Matplotlib figure — square, no border
    fig = plt.figure(figsize=(2, 2), dpi=256, facecolor="white")
    ax  = fig.add_axes([0, 0, 1, 1])  # full‑bleed axes
    ax.set_aspect('equal', adjustable='box')
    ax.axis('off')

    # rotate & project
    R        = rot_xyz(math.radians(roll_deg), math.radians(PITCH_DEG), math.radians(YAW_DEG))
    verts2d  = project_ortho(V @ R.T)

    # draw circles
    for x, y in verts2d:
        ax.add_patch(Circle((x, y), CIRCLE_R, color='black', zorder=1))

    # draw full edges (round caps)
    for i, j in EDGES:
        (x1, y1), (x2, y2) = verts2d[[i, j]]
        ax.plot([x1, x2], [y1, y2], lw=LINE_W,
                color='white', solid_capstyle='round', zorder=2)

    # fixed limits to keep size constant
    ax.set_xlim(-HALF_FRAME, HALF_FRAME)
    ax.set_ylim(-HALF_FRAME, HALF_FRAME)
    ax.invert_yaxis()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=256, bbox_inches='tight', pad_inches=0)
    plt.close(fig)
    return buf.getvalue()

# ─────────────────────────── avatar update logic ─────────────────────────

def compute_deg(now_utc: dt.datetime | None = None) -> int:
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    elapsed_min = int((now - START_DATETIME).total_seconds() // 60)
    steps       = elapsed_min // 15           # integer 15‑min buckets
    deg   = (steps * 7) % 360           # wrap at 360
    return deg


def update_bluesky_avatar(now_utc: dt.datetime | None = None, dry_run=False):
    handle   = os.getenv('BLUESKY_HANDLE')
    app_pw   = os.getenv('BLUESKY_APP_PASSWORD')
    if not handle or not app_pw:
        raise RuntimeError('BLUESKY_HANDLE and BLUESKY_APP_PASSWORD must be set')

    roll = compute_deg(now_utc)
    png = render_frame(roll)

    if dry_run:
        with open(f'cube-{roll}.png', 'wb') as f:
            f.write(png)
        return

    client = Client()
    client.login(handle, app_pw)

    old_description = old_display_name = old_banner = None

    try:
        current_profile_record = client.app.bsky.actor.profile.get(client.me.did, 'self')
        current_profile = current_profile_record.value
        swap_record_cid = current_profile_record.cid
        old_description = current_profile.description
        old_display_name = current_profile.display_name
        old_banner = current_profile.banner
        old_avatar = current_profile.avatar

    except BadRequestError:
        current_profile = swap_record_cid = None

    # upload blob
    blob_resp = client.upload_blob(png)


    client.com.atproto.repo.put_record(
        models.ComAtprotoRepoPutRecord.Data(
            collection=models.ids.AppBskyActorProfile,
            repo=client.me.did,
            rkey='self',
            swap_record=swap_record_cid,
            record=models.AppBskyActorProfile.Record(
                avatar=blob_resp.blob,
                banner=old_banner,
                description=old_description,
                display_name=old_display_name,
            ),
        )
    )


    print(f"updated avatar → roll={roll}° (elapsed {((dt.datetime.now(dt.timezone.utc)-START_DATETIME).total_seconds()//60)} min)")


def sweep_through_images():
    INCREMENT = dt.timedelta(minutes=15)
    timestamps = [START_DATETIME + i * INCREMENT for i in range(13)]
    for ts in timestamps:
        update_bluesky_avatar(now_utc=ts, dry_run=True)


# ─────────────────────────── CLI entry point  ────────────────────────────
if __name__ == '__main__':
    load_dotenv()
    #sweep_through_images()
    update_bluesky_avatar(dry_run=False)
