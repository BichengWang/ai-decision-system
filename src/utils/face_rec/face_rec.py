import os
import cv2
import torch
import logging
import numpy as np
from deepface import DeepFace
from deepface.commons import functions


logger = logging.getLogger(__name__)

# Global configuration
SAMPLE_INTERVAL = 60  # seconds between samples
DETECTOR_BACKEND = "retinaface"  # More accurate face detection
MODEL_NAME = "ArcFace"  # State-of-the-art face recognition model
DISTANCE_METRIC = "cosine"  # Better distance metric for face matching


def recognize_faces(image, known_encodings, known_names):
    """Recognize faces in an image using known encodings."""
    try:
        # Detect faces using DeepFace
        face_objs = DeepFace.extract_faces(
            img_path=image,
            target_size=(112, 112),
            detector_backend=DETECTOR_BACKEND,
            enforce_detection=True
        )
        
        names = []
        for face_obj in face_objs:
            # Get face embedding
            embedding = DeepFace.represent(
                img_path=face_obj["face"],
                model_name=MODEL_NAME,
                detector_backend=DETECTOR_BACKEND,
                enforce_detection=False
            )[0]["embedding"]
            
            # Compare with known faces
            distances = []
            for known_encoding in known_encodings:
                distance = functions.find_distance(
                    embedding, 
                    known_encoding, 
                    distance_metric=DISTANCE_METRIC
                )
                distances.append(distance)
            
            # Find best match
            min_distance = min(distances)
            if min_distance < 0.4:  # Threshold for face matching
                matched_idx = distances.index(min_distance)
                names.append(known_names[matched_idx])
            else:
                names.append("Unknown")
                
        return names
    except Exception as e:
        logger.error(f"Error in face recognition: {str(e)}")
        return []


def create_face_encoding(image_path):
    """Create a face encoding from a single image."""
    try:
        embedding = DeepFace.represent(
            img_path=image_path,
            model_name=MODEL_NAME,
            detector_backend=DETECTOR_BACKEND
        )[0]["embedding"]
        return embedding
    except Exception as e:
        logger.error(f"Error creating face encoding: {str(e)}")
        return None


def extract_encodings_from_video(video_path, frame_interval=SAMPLE_INTERVAL):
    """Extract face encodings from a video file at regular intervals."""
    video_capture = cv2.VideoCapture(video_path)
    if not video_capture.isOpened():
        raise ValueError(f"Could not open video file: {video_path}")
        
    encodings = []
    fps = video_capture.get(cv2.CAP_PROP_FPS)
    total_frames = int(video_capture.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_gap = int(fps * frame_interval)
    
    target_frames = list(range(0, total_frames, frame_gap))
    logger.info(f"Extracting encodings from {len(target_frames)} frames")
    
    for frame_idx in target_frames:
        video_capture.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        success, frame = video_capture.read()
        if success:
            try:
                # Save frame temporarily
                temp_path = "temp_frame.jpg"
                cv2.imwrite(temp_path, frame)
                
                # Extract face embeddings
                embedding = create_face_encoding(temp_path)
                if embedding is not None:
                    encodings.append(embedding)
                
                # Clean up
                os.remove(temp_path)
            except Exception as e:
                logger.error(f"Error processing frame {frame_idx}: {str(e)}")
            
    video_capture.release()
    logger.info(f"Extracted {len(encodings)} face encodings")
    return encodings


def build_known_faces_encodings(root_dir, max_videos_per_folder=1):
    """Build known face encodings from sub-folders containing MP4 videos."""
    known_encodings = []
    known_names = []

    for name in os.listdir(root_dir):
        person_folder = os.path.join(root_dir, name)
        if not os.path.isdir(person_folder):
            continue
        videos_processed = 0
        for subdir, _, files in os.walk(person_folder):
            for video_file in files:
                if video_file.lower().endswith(".mp4"):
                    if videos_processed >= max_videos_per_folder:
                        break
                    logger.info(f"Processing {video_file}...")
                    video_path = os.path.join(subdir, video_file)
                    try:
                        encodings = extract_encodings_from_video(video_path)
                        if encodings:
                            known_encodings.extend(encodings)
                            known_names.extend([name] * len(encodings))
                            videos_processed += 1
                    except Exception as e:
                        logger.error(f"Error processing {video_file}: {str(e)}")
            if videos_processed >= max_videos_per_folder:
                break

    return known_encodings, known_names


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if not torch.cuda.is_available():
        logger.warning("GPU not available. Running on CPU.")
    else:
        logger.info("GPU detected. Running on GPU.")

    logger.info("Building face recognition index...")
    root_directory = "/mnt/d/download/train"
    known_encodings, known_names = build_known_faces_encodings(root_directory)
    logger.info(f"Built encodings for {len(set(known_names))} individuals")

    logger.info("Testing face recognition on evaluation case...")
    eval_video_path = "/mnt/d/download/pred/*.mp4"
    try:
        eval_encodings = extract_encodings_from_video(eval_video_path)
        
        if not eval_encodings:
            logger.info("No faces detected in evaluation video")
        else:
            for i, eval_encoding in enumerate(eval_encodings):
                distances = []
                for known_encoding in known_encodings:
                    distance = functions.find_distance(
                        eval_encoding, 
                        known_encoding, 
                        distance_metric=DISTANCE_METRIC
                    )
                    distances.append(distance)
                
                min_distance = min(distances)
                if min_distance < 0.4:
                    matched_idx = distances.index(min_distance)
                    logger.info(f"Face {i+1} matches with: {known_names[matched_idx]}")
                else:
                    logger.info(f"Face {i+1} does not match any known individual")
    except Exception as e:
        logger.error(f"Error processing evaluation video: {str(e)}")
