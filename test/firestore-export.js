const { initializeApp, cert } = require('firebase-admin/app');
const { getFirestore } = require('firebase-admin/firestore');
const fs = require('fs');
const path = require('path');

// 1. Path to your downloaded service account key file
const serviceAccountPath = path.join(__dirname, 'service-account.json');

// 2. CONFIGURATION: Change this to your target collection name
const COLLECTION_NAME = 'trainwatch_load_test_runs'; 
const OUTPUT_FILE = `${COLLECTION_NAME}_export.json`;

// Verify the service account file exists before starting
if (!fs.existsSync(serviceAccountPath)) {
  console.error(`Error: 'service-account.json' not found in ${__dirname}`);
  process.exit(1);
}

// 3. Updated Initialization Method
const serviceAccount = require(serviceAccountPath);

initializeApp({
  credential: cert(serviceAccount)
});

const db = getFirestore();

// ... The rest of your async function exportCollection() stays exactly the same ...


async function exportCollection() {
  console.log(`Connecting to Firestore and fetching collection: "${COLLECTION_NAME}"...`);
  
  try {
    const snapshot = await db.collection(COLLECTION_NAME).get();
    
    if (snapshot.empty) {
      console.log('No matching documents found.');
      return;
    }

    const documentsArray = [];
    
    // Loop through documents and extract data along with the Document ID
    snapshot.forEach(doc => {
      documentsArray.push({
        _id: doc.id, // Includes the document's ID
        ...doc.data() // Spreads the document fields
      });
    });

    // 4. Save the array as a beautifully formatted JSON file
    fs.writeFileSync(OUTPUT_FILE, JSON.stringify(documentsArray, null, 2), 'utf-8');
    
    console.log(`\x1b[32m%s\x1b[0m`, `Success! Successfully exported ${documentsArray.length} documents.`);
    console.log(`Saved to: ${path.join(__dirname, OUTPUT_FILE)}`);

  } catch (error) {
    console.error('Error exporting collection:', error);
  }
}

// Execute the script
exportCollection();
