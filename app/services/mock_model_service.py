import random
import time


class MockModelService:
    model_version = "mock-v1"

    def predict(self, image_path: str) -> dict:
        start_time = time.perf_counter()

        time.sleep(1)

        labels = [
            "normal",
            "scratch",
            "crack",
            "stain",
            "shape_defect",
        ]

        predicted_label = random.choice(labels)
        confidence = round(random.uniform(0.65, 0.98), 4)
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        return {
            "predicted_label": predicted_label,
            "confidence": confidence,
            "model_version": self.model_version,
            "latency_ms": latency_ms,
        }


mock_model_service = MockModelService()