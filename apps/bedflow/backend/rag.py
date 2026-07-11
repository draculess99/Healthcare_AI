import os
import glob
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

POLICY_DIR = "database/policies"

class RAGSystem:
    def __init__(self):
        self.documents = []
        self.vectorizer = TfidfVectorizer(stop_words='english')
        self.tfidf_matrix = None
        self.load_policies()

    def load_policies(self):
        if not os.path.exists(POLICY_DIR):
            return
            
        files = glob.glob(os.path.join(POLICY_DIR, "*.txt"))
        for file in files:
            with open(file, "r") as f:
                content = f.read()
                if content.strip():
                    self.documents.append(content)
                    
        if self.documents:
            self.tfidf_matrix = self.vectorizer.fit_transform(self.documents)

    def retrieve_policies(self, query, top_k=1):
        if not self.documents or not query.strip():
            return ""
            
        query_vec = self.vectorizer.transform([query])
        similarities = cosine_similarity(query_vec, self.tfidf_matrix).flatten()
        
        # Get top k indices sorted by similarity score
        top_indices = similarities.argsort()[-top_k:][::-1]
        
        results = []
        for idx in top_indices:
            if similarities[idx] > 0.05: # Minimum threshold
                results.append(self.documents[idx])
                
        if results:
            return "\n\n".join(results)
        return ""

# Singleton instance to hold embeddings in memory
rag_system = RAGSystem()

def get_relevant_policy(query):
    return rag_system.retrieve_policies(query)
