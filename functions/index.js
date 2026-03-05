const functions = require('firebase-functions');
const admin = require('firebase-admin');

// Initialize Firebase Admin SDK
admin.initializeApp();
const db = admin.firestore();

exports.mcp = functions.https.onRequest(async (req, res) => {
  // Ensure only POST requests are accepted for data modification, GET for reading
  if (req.method === 'OPTIONS') {
    // Handle CORS preflight requests
    res.set('Access-Control-Allow-Origin', '*');
    res.set('Access-Control-Allow-Methods', 'GET, POST, DELETE');
    res.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    res.status(204).send('');
    return;
  }
  
  // Set CORS headers for actual requests
  res.set('Access-Control-Allow-Origin', '*');

  try {
    const { action, name, creator, type, nominationId } = req.body;

    switch (action) {
      case 'addNomination':
        if (!name || !creator || !type) {
          return res.status(400).json({ status: 'error', message: 'Missing required fields for addNomination' });
        }
        if (type !== 'hero' && type !== 'encounter') {
          return res.status(400).json({ status: 'error', message: 'Type must be "hero" or "encounter"' });
        }

        const newNominationRef = await db.collection('nominations').add({
          name,
          creator,
          type,
          timestamp: admin.firestore.FieldValue.serverTimestamp()
        });
        return res.status(201).json({ status: 'success', message: 'Nomination added', id: newNominationRef.id });

      case 'getNominations':
        const nominationsSnapshot = await db.collection('nominations').orderBy('timestamp', 'desc').get();
        const nominations = nominationsSnapshot.docs.map(doc => ({
          id: doc.id,
          ...doc.data()
        }));
        return res.status(200).json({ status: 'success', nominations });

      case 'deleteNomination':
        if (!nominationId) {
          return res.status(400).json({ status: 'error', message: 'Missing nominationId for deleteNomination' });
        }
        await db.collection('nominations').doc(nominationId).delete();
        return res.status(200).json({ status: 'success', message: 'Nomination deleted' });

      default:
        return res.status(400).json({ status: 'error', message: 'Unknown action' });
    }
  } catch (error) {
    console.error('Error in MCP Cloud Function:', error);
    return res.status(500).json({ status: 'error', message: 'Internal server error', details: error.message });
  }
});
