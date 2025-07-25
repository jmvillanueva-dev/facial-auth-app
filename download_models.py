import tensorflow_hub as hub
import os

MODEL_DIR = "tf_models"


def download_model(model_url, model_name):
    print(f"Downloading {model_name} from {model_url}...")
    # hub.load descargará y guardará el modelo en la carpeta especificada
    hub.load(model_url, tags=None, signature=None, as_expected=True)
    print(f"{model_name} downloaded successfully.")


def main():
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR)

    # El Faster R-CNN detection model
    faster_rcnn_url = "https://tfhub.dev/tensorflow/faster_rcnn/resnet101_v1_640x640/1"
    # El InceptionResNetV2 feature vector model
    inception_resnet_url = (
        "https://tfhub.dev/google/imagenet/inception_resnet_v2/feature_vector/4"
    )

    # Set the TFHUB_CACHE_DIR environment variable
    os.environ["TFHUB_CACHE_DIR"] = os.path.abspath(MODEL_DIR)

    download_model(faster_rcnn_url, "Faster R-CNN")
    download_model(inception_resnet_url, "InceptionResNetV2")

    print("All models downloaded to the local cache.")


if __name__ == "__main__":
    main()
