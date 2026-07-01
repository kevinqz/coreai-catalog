# On-Device RAG with EmbeddingGemma 300M

Private retrieval-augmented generation using local embeddings.
All text stays on-device — no API calls, no data collection.

## Setup

```bash
pip install git+https://github.com/kevinqz/coreai-catalog.git
coreai-catalog install embeddinggemma-300m
```

Artifact: https://huggingface.co/mlboydaisuke/embeddinggemma-300m-CoreAI

## Integration

```swift
import CoreAI

/// On-device embedding engine for semantic search and RAG.
/// Converts text into dense vectors for similarity matching.
class EmbeddingEngine {
    private let model: CoreAIModel

    init() throws {
        guard let bundleURL = Bundle.main.url(forResource: "embeddinggemma-300m", withExtension: "aimodel") else {
            throw EmbeddingError.bundleNotFound
        }
        model = try CoreAIModel(contentsOf: bundleURL)
    }

    /// Generate an embedding vector for a piece of text.
    /// - Parameter text: Input text to embed
    /// - Returns: Dense vector (typically 768 or 1536 dimensions)
    func embed(_ text: String) async throws -> [Float] {
        let request = CoreAIRequest.input(text: text)
        let response = try await model.predict(request)
        return response.vector
    }

    /// Compute cosine similarity between two embedding vectors.
    /// - Returns: Similarity score in [-1, 1]
    func cosineSimilarity(_ a: [Float], _ b: [Float]) -> Float {
        guard a.count == b.count else { return 0 }
        var dot: Float = 0
        var normA: Float = 0
        var normB: Float = 0
        for i in 0..<a.count {
            dot += a[i] * b[i]
            normA += a[i] * a[i]
            normB += b[i] * b[i]
        }
        let denom = sqrt(normA) * sqrt(normB)
        return denom > 0 ? dot / denom : 0
    }
}

/// Simple in-memory document store with semantic search.
class VectorStore {
    private let engine: EmbeddingEngine
    private var documents: [(text: String, embedding: [Float])] = []

    init(engine: EmbeddingEngine) {
        self.engine = engine
    }

    /// Add a document to the store.
    func add(_ text: String) async throws {
        let embedding = try await engine.embed(text)
        documents.append((text, embedding))
    }

    /// Search for the top-k most similar documents.
    /// - Parameters:
    ///   - query: Search query text
    ///   - topK: Number of results to return
    /// - Returns: Array of (text, score) pairs, sorted by relevance
    func search(_ query: String, topK: Int = 5) async throws -> [(text: String, score: Float)] {
        let queryEmbedding = try await engine.embed(query)
        var scored = documents.map { doc in
            (doc.text, engine.cosineSimilarity(queryEmbedding, doc.embedding))
        }
        scored.sort { $0.1 > $1.1 }
        return Array(scored.prefix(topK))
    }
}

enum EmbeddingError: Error {
    case bundleNotFound
}
```

## Usage: On-device RAG pipeline

```swift
/// Build a private knowledge base and query it — all on-device.
func runRAGExample() async {
    let engine = try! EmbeddingEngine()
    let store = VectorStore(engine: engine)

    // Index your documents
    try! await store.add("The iPhone 17 Pro has a 6.3-inch OLED display with ProMotion at 120Hz.")
    try! await store.add("Apple Silicon M5 chip features a 10-core CPU and 16-core GPU.")
    try! await store.add("Core AI models run on the Neural Engine for maximum privacy and efficiency.")

    // Query
    let results = try! await store.search("What display does the iPhone have?", topK: 3)
    for result in results {
        print("Score: \(result.score) — \(result.text)")
    }
    // Output:
    // Score: 0.87 — The iPhone 17 Pro has a 6.3-inch OLED display...
    // Score: 0.42 — Apple Silicon M5 chip features...
    // Score: 0.31 — Core AI models run on...
}
```

## Capabilities

| Feature | Support |
|---|---|
| Device | iPhone, iPad, Mac |
| Offline | ✅ Fully on-device |
| License | Apache-2.0 (commercial use: likely) |
| Parameters | 300M |
| Architecture | Transformer (encoder) |
| Output | Dense vector embedding |

## Tips

- For large document collections, persist embeddings in a local SQLite database
- Chunk long documents into 256-512 token segments for best retrieval quality
- Normalize embeddings (L2) before storing to speed up similarity computation
- Pair with an LLM (e.g., Qwen3 0.6B) for full RAG: retrieve with embeddings, generate with LLM
