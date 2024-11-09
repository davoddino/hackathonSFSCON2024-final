import time
import cv2
import mediapipe as mp
import numpy as np
import asyncio
import websockets

mp_pose = mp.solutions.pose

def calculate_angle(a, b, c):
    a = np.array([a.x, a.y])
    b = np.array([b.x, b.y])
    c = np.array([c.x, c.y])

    radians = np.arctan2(c[1] - b[1], c[0] - b[0]) - np.arctan2(a[1] - b[1], a[0] - b[0])
    angle = np.abs(np.degrees(radians))
    if angle > 180.0:
        angle = 360 - angle
    return angle

def are_both_arms_raised(landmarks, angle_margin=40):
    left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
    right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
    left_elbow = landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value]
    right_elbow = landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value]
    left_wrist = landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value]
    right_wrist = landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value]

    left_arm_raised = left_wrist.visibility > 0.5 and left_wrist.y < left_shoulder.y
    right_arm_raised = right_wrist.visibility > 0.5 and right_wrist.y < right_shoulder.y

    if not (left_arm_raised and right_arm_raised):
        return False

    left_arm_angle = calculate_angle(left_shoulder, left_elbow, left_wrist)
    right_arm_angle = calculate_angle(right_shoulder, right_elbow, right_wrist)

    left_arm_extended = 180 - angle_margin <= left_arm_angle <= 180 + angle_margin
    right_arm_extended = 180 - angle_margin <= right_arm_angle <= 180 + angle_margin

    return left_arm_extended and right_arm_extended

def check_collision(landmarks, ball_center, ball_radius, image_width, image_height):
    for landmark in landmarks:
        x_px = int(landmark.x * image_width)
        y_px = int(landmark.y * image_height)
        distance = np.sqrt((x_px - ball_center[0]) ** 2 + (y_px - ball_center[1]) ** 2)
        if distance <= ball_radius:
            return True
    return False

async def person_detection_server(websocket, path):
    global cap, pose, global_arms_raised, arm_raise_start_time, prev_message, game_active

    while True:
        ret, frame = cap.read()
        if not ret:
            await sendStatusChanged(websocket, "No camera feed.")
            break

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(frame_rgb)

        if results.pose_landmarks:
            if game_active:
                # Logica del mini-gioco
                if results.segmentation_mask is not None:
                    condition = np.stack((results.segmentation_mask,) * 3, axis=-1) > 0.1
                    bg_image = np.zeros(frame.shape, dtype=np.uint8)
                    bg_image[:] = (0, 0, 0)  # Sfondo nero
                    segmented_image = np.where(condition, frame, bg_image)
                else:
                    segmented_image = frame.copy()

                # Disegna la palla rossa
                ball_center = (frame.shape[1] - 50, 50)
                ball_radius = 20
                ball_color = (0, 0, 255)
                cv2.circle(segmented_image, ball_center, ball_radius, ball_color, -1)

                # Controlla la collisione
                image_height, image_width, _ = frame.shape
                collision = check_collision(results.pose_landmarks.landmark, ball_center, ball_radius, image_width, image_height)
                if collision:
                    print("Collision detected!")
                    cv2.putText(segmented_image, 'Congratulazioni!', (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 2, (0,255,0), 3)
                    # Invia il messaggio "Congratulations" al client
                    await sendStatusChanged(websocket, "Congratulations")
                    # Continua a inviare i frame con il messaggio per un breve periodo
                    for _ in range(30):  # Circa 1 secondo a 30 fps
                        _, buffer = cv2.imencode('.jpg', segmented_image)
                        frame_bytes = buffer.tobytes()
                        await websocket.send(frame_bytes)
                        await asyncio.sleep(1/30)
                    # Termina il gioco
                    game_active = False
                    global_arms_raised = False
                    arm_raise_start_time = None
                else:
                    # Continua a inviare i frame del gioco
                    _, buffer = cv2.imencode('.jpg', segmented_image)
                    frame_bytes = buffer.tobytes()
                    await websocket.send(frame_bytes)
            else:
                # Controlla se le braccia sono alzate per avviare il gioco
                if are_both_arms_raised(results.pose_landmarks.landmark):
                    if not global_arms_raised:
                        global_arms_raised = True
                        arm_raise_start_time = time.time()
                    elif time.time() - arm_raise_start_time >= 3:
                        game_active = True
                        print("Gioco avviato!")
                        await sendStatusChanged(websocket, "Game Started")
                else:
                    global_arms_raised = False
                    arm_raise_start_time = None
                    await sendStatusChanged(websocket, "Person detected but arms not raised")
        else:
            await sendStatusChanged(websocket, "No person detected")

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    pose.close()

async def sendStatusChanged(websocket, message):
    global prev_message
    if message != prev_message:
        await websocket.send(message)
        prev_message = message

async def main():
    global cap, pose, global_arms_raised, arm_raise_start_time, prev_message, game_active
    cap = cv2.VideoCapture(0)
    pose = mp_pose.Pose(static_image_mode=False, model_complexity=1, enable_segmentation=True, min_detection_confidence=0.5)
    global_arms_raised = False
    arm_raise_start_time = None
    prev_message = ""
    game_active = False

    async with websockets.serve(person_detection_server, "localhost", 6789):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())