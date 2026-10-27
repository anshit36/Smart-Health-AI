import * as dotenv from 'dotenv';
dotenv.config();

import * as fs from 'fs';
import * as path from 'path';
import { PDFLoader } from '@langchain/community/document_loaders/fs/pdf';
import { RecursiveCharacterTextSplitter } from '@langchain/textsplitters';
import { ChromaClient } from 'chromadb';
import ollama from 'ollama';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function getEmbedding(text) {
    const response = await ollama.embeddings({
        model: 'nomic-embed-text',
        prompt: text
    });
    return response.embedding;
}

async function indexDocument() {
    console.log("=========================================");
    console.log("🚀 OFFLINE INDEXING WITH OLLAMA + CHROMADB");
    console.log("=========================================\n");

    const docsPath = path.resolve('./who');

    if (!fs.existsSync(docsPath)) {
        console.error(`❌ ERROR: The folder "${docsPath}" does not exist!`);
        process.exit(1);
    }

    const fileNames = fs.readdirSync(docsPath).filter(f => f.endsWith('.pdf'));
    console.log(`[STEP 1] Found ${fileNames.length} PDFs. Extracting text...\n`);

    let rawDocs = [];
    for (const file of fileNames) {
        try {
            const docs = await new PDFLoader(path.join(docsPath, file)).load();
            rawDocs = rawDocs.concat(docs);
            process.stdout.write(`  ✅ ${file}\n`);
        } catch (e) {
            console.warn(`  ⚠️ Skipping ${file}`);
        }
    }

    const textSplitter = new RecursiveCharacterTextSplitter({ chunkSize: 1000, chunkOverlap: 200 });
    let chunkedDocs = await textSplitter.splitDocuments(rawDocs);
    chunkedDocs = chunkedDocs.filter(doc => doc.pageContent.replace(/\s/g, '').length > 50);
    console.log(`\n✅ Total chunks: ${chunkedDocs.length}\n`);

    // Test embedding
    console.log("[STEP 2] Testing Ollama embedding...");
    try {
        const testVec = await getEmbedding("test health query");
        console.log(`✅ Works! Dimension = ${testVec.length}\n`);
    } catch (e) {
        console.error("❌ Ollama embedding failed:", e.message);
        console.error("Make sure Ollama is running: ollama serve");
        process.exit(1);
    }

    // Setup ChromaDB
    const chroma = new ChromaClient({ path: "http://localhost:8000" });
    
    // Delete existing collection if exists
    try {
        await chroma.deleteCollection({ name: "who_health" });
        console.log("🗑️ Deleted existing collection\n");
    } catch (e) {
        // Collection doesn't exist yet, that's fine
    }

    const collection = await chroma.createCollection({ 
        name: "who_health",
        metadata: { "hnsw:space": "cosine" }
    });

    console.log("=========================================");
    console.log(`⏳ [STEP 3] UPLOADING ${chunkedDocs.length} CHUNKS TO CHROMADB`);
    console.log("=========================================\n");

    const BATCH_SIZE = 25;
    let totalUploaded = 0;
    const totalBatches = Math.ceil(chunkedDocs.length / BATCH_SIZE);

    for (let i = 0; i < chunkedDocs.length; i += BATCH_SIZE) {
        const batch = chunkedDocs.slice(i, i + BATCH_SIZE);
        const batchNum = Math.floor(i / BATCH_SIZE) + 1;
        process.stdout.write(`📦 Batch ${batchNum}/${totalBatches}... `);

        const ids = [];
        const embeddings = [];
        const documents = [];
        const metadatas = [];

        for (let j = 0; j < batch.length; j++) {
            try {
                const vector = await getEmbedding(batch[j].pageContent);
                ids.push(`chunk-${i + j}`);
                embeddings.push(vector);
                documents.push(batch[j].pageContent);
                metadatas.push({ source: batch[j].metadata?.source || 'unknown' });
            } catch (err) {
                console.warn(`  ⚠️ Skipping chunk ${i + j}`);
            }
            await sleep(50);
        }

        if (ids.length > 0) {
            await collection.add({ ids, embeddings, documents, metadatas });
            totalUploaded += ids.length;
        }

        const pct = ((i + batch.length) / chunkedDocs.length * 100).toFixed(1);
        console.log(`✅ ${totalUploaded} uploaded (${pct}%)`);
    }

    console.log("\n=========================================");
    console.log(`🎉 DONE! Uploaded ${totalUploaded} chunks to ChromaDB`);
    console.log("ChromaDB data saved locally — no internet needed!");
    console.log("=========================================");
}

indexDocument().catch(err => {
    console.error("\n💥 FATAL ERROR:", err.message);
    process.exit(1);
});
