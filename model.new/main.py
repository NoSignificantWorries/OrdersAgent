import time

from sentence_transformers import SentenceTransformer


def main():
    model = SentenceTransformer("sergeyzh/rubert-tiny-turbo")

    a = time.time()
    embedding = model.encode("Рассчитайте пожалуйста эту заявку, сколько выйдет?")
    b = time.time()
    print(b - a)

    print(f"Форма вектора: {embedding.shape}")
    print(f"Первые 5 значений: {embedding[:5]}")


if __name__ == "__main__":
    main()
