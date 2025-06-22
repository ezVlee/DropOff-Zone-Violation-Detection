from flask import Flask, render_template, Response, request
from flask_socketio import SocketIO
import cv2
import time
import numpy as np
from ultralytics import YOLO
import requests
import subprocess
import threading
from collections import OrderedDict
import warnings
import json

app = Flask(__name__, static_folder='static')
socketio = SocketIO(app, cors_allowed_origins="*")

model = YOLO("yolo/yolo11n.pt")

PARKING_AREA = np.array([
    (20, 700),
    (1250, 700),
    (1100, 100),
    (150, 100)
], np.int32)

VALID_CLASSES = [2, 3]
THRESHOLD_TIME = 5
DISAPPEAR_LIMIT = 10

vehicle_tracker = OrderedDict()
next_vehicle_id = 1

TELEGRAM_TOKEN = "*****"
TELEGRAM_CHAT_ID = "*********"
telegram_response_status = {}

warnings.filterwarnings("ignore", category=UserWarning, module='cv2')

# Di global scope, ganti telegram_response_status dengan satu counter saja:
telegram_counter = 0
telegram_done = 0



def send_telegram(message, vehicle_id):
    global telegram_counter

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Done", "callback_data": f"done_{vehicle_id}"}
        ]]
    }
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "reply_markup": json.dumps(keyboard)
    }

    try:
        resp = requests.post(url, data=data)
        if resp.status_code != 200:
            print("Telegram Error:", resp.text)
            return

        # setiap notifikasi terkirim, counter +1
        telegram_counter += 1
        # kirim ke frontend
        socketio.emit('update_stats', {
            "respon": telegram_counter,    # gunakan sebagai “pelanggaran” di UI
            "pelanggaran": telegram_counter  # atau jika mau dibalik namanya
        })

    except Exception as e:
        print("Gagal kirim Telegram:", e)


def is_inside_parking(x1, y1, x2, y2):
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    return cv2.pointPolygonTest(PARKING_AREA, (cx, cy), False) >= 0


def euclidean_distance(p1, p2):
    return np.linalg.norm(np.array(p1) - np.array(p2))


def assign_vehicle_id(centroid):
    global next_vehicle_id
    for vid, data in vehicle_tracker.items():
        if euclidean_distance(centroid, data["centroid"]) < 50:
            data["centroid"] = centroid
            data["frames_absent"] = 0
            return vid
    vehicle_tracker[next_vehicle_id] = {
        "centroid": centroid,
        "frames_absent": 0,
        "time_entered": time.time(),
        "notified": False
    }
    next_vehicle_id += 1
    return next_vehicle_id - 1


def handle_countdown(vehicle_id):
    countdown_time = 100
    for i in range(countdown_time, 0, -1):
        # Jika kendaraan sudah merespon
        if telegram_response_status.get(vehicle_id) == 0:
            return

        # Jika kendaraan sudah tidak terdeteksi (sudah meninggalkan area)
        if vehicle_id not in vehicle_tracker or vehicle_tracker[vehicle_id]["frames_absent"] > DISAPPEAR_LIMIT:
            msg = f"✅ Kendaraan ID {vehicle_id} sudah meninggalkan area sebelum countdown selesai."
            print(f"[INFO] {msg}")
            socketio.emit('notification', {'message': msg, 'alert': False})

            # Reset status Telegram dan pelanggaran
            telegram_response_status.pop(vehicle_id, None)  # Reset status Telegram
            socketio.emit('telegram_status', {'vehicle_id': vehicle_id, 'status': 0})  # Reset status Telegram di UI

            # Reset penghitung pelanggaran dan respon ke 0
            global telegram_counter, telegram_done
            telegram_counter = 0
            telegram_done = 0

            # Emit reset status pelanggaran dan respon
            socketio.emit('update_stats', {
                "respon": telegram_done,  # Reset statistik respon ke 0
                "pelanggaran": telegram_counter  # Reset statistik pelanggaran ke 0
            })

            return

        socketio.emit('countdown_update', {'vehicle_id': vehicle_id, 'time_left': i})
        time.sleep(1)

    # Countdown habis, kirim notifikasi pelanggaran ulang
    if telegram_response_status.get(vehicle_id) != 0:
        msg = f"🚨 Pelanggaran ulang: Kendaraan ID {vehicle_id} tidak merespon dalam 100 detik!"
        socketio.emit('notification', {'message': msg, 'alert': True})
        send_telegram(msg, vehicle_id)

        # Reset penghitung pelanggaran dan respon ke 1
        telegram_counter += 1  # Increment pelanggaran setelah countdown habis
        telegram_done = 1  # Menghitung respon untuk pelanggaran pertama
        socketio.emit('update_stats', {"pelanggaran": telegram_counter, "respon": telegram_done})
        socketio.emit('telegram_status', {'vehicle_id': vehicle_id, 'status': 1})


def generate_frames():
    cap = cv2.VideoCapture('http://**IP**:8080/?action=stream')
    if not cap.isOpened():
        while True:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "No Camera Detected", (150, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            _, buffer = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes())
        return

    global vehicle_tracker
    while True:
        success, frame = cap.read()
        if not success:
            break

        results = model(frame)
        detected_vehicles = set()

        for result in results:
            for box in result.boxes:
                cls = int(box.cls[0])
                if cls in VALID_CLASSES:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    centroid = ((x1 + x2) // 2, (y1 + y2) // 2)
                    vehicle_id = assign_vehicle_id(centroid)
                    detected_vehicles.add(vehicle_id)

                    if is_inside_parking(x1, y1, x2, y2):
                        tracked = vehicle_tracker[vehicle_id]
                        parked_time = time.time() - tracked["time_entered"]

                        if parked_time > THRESHOLD_TIME and not tracked["notified"]:
                            msg = f"🚨 Pelanggaran: Kendaraan ID {vehicle_id} parkir lebih dari {THRESHOLD_TIME} detik!"
                            socketio.emit('notification', {'message': msg, 'alert': True})
                            send_telegram(msg, vehicle_id)
                            threading.Thread(target=handle_countdown, args=(vehicle_id,)).start()
                            tracked["notified"] = True

                        box_color = (0, 0, 255)
                    else:
                        box_color = (0, 255, 0)

                    cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
                    cv2.putText(frame, f"ID {vehicle_id}", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        for vid in list(vehicle_tracker.keys()):
            if vid not in detected_vehicles:
                vehicle_tracker[vid]["frames_absent"] += 1
                if vehicle_tracker[vid]["frames_absent"] > DISAPPEAR_LIMIT:
                    del vehicle_tracker[vid]

        cv2.polylines(frame, [PARKING_AREA], isClosed=True, color=(0, 255, 255), thickness=2)
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        cv2.putText(frame, timestamp, (10, 470),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1)

        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes())

    cap.release()



@app.route('/')
def index():
    return render_template('index.html')


@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/test_emit')
def test_emit():
    socketio.emit('notification', {'message': '🔔 Ini tes notifikasi!', 'alert': True})
    return "Emit sent"


@app.route('/set_audio_output', methods=['POST'])
def set_audio_output():
    data = request.get_json()
    device = data.get('device')
    try:
        subprocess.run(['wpctl', 'set-default', device], check=True)
        return "Output diubah", 200
    except Exception as e:
        return f"Error: {str(e)}", 500


@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    global telegram_counter, telegram_done
    data = request.get_json()

    if 'callback_query' in data and data['callback_query']['data'].startswith('done_'):
        vid = int(data['callback_query']['data'].split('_')[1])

        # Kurangi respon dan pelanggaran
        telegram_counter = max(0, telegram_counter - 1)
        telegram_done = max(0, telegram_done - 1)

        # Edit pesan di Telegram
        chat = data['callback_query']['message']['chat']['id']
        mid = data['callback_query']['message']['message_id']
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText",
            data={
                "chat_id": chat,
                "message_id": mid,
                "text": f"✅ Kendaraan ID {vid} telah dikonfirmasi selesai oleh petugas."
            }
        )

        # Hapus data kendaraan
        vehicle_tracker.pop(vid, None)
        telegram_response_status.pop(vid, None)

        # Reset total jika kosong
        if not vehicle_tracker:
            telegram_counter = 0
            telegram_done = 0

        # Emit ke UI setelah semua update
        socketio.emit('update_stats', {
            "respon": telegram_done,
            "pelanggaran": telegram_counter
        })
        socketio.emit('cancel_countdown', {'vehicle_id': vid})

        print(f"[WEBHOOK] Done ditekan untuk kendaraan ID {vid}")
        print(f"[SOCKET] Update stats: Respon={telegram_done}, Pelanggaran={telegram_counter}")
    
    return "OK", 200


@app.route('/status')
def status():
    return telegram_response_status


@app.route('/reset_all', methods=['POST'])
def reset_all():
    vehicle_tracker.clear()
    telegram_response_status.clear()
    socketio.emit('update_stats', {"respon": 0, "pelanggaran": 0})
    return "Semua data telah direset", 200


@socketio.on("play_mic")
def handle_play_mic():
    def play_sound():
        try:
            subprocess.run([
                "C:\\ffmpeg\\bin\\ffplay.exe", "-nodisp", "-autoexit",
                "static/sound/violation_alert.mp3"
            ], check=True)
        except Exception as e:
            print(f"[ERROR] Failed to play audio: {e}")

    threading.Thread(target=play_sound).start()


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
  