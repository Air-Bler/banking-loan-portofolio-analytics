// English / Greek for the dashboard. English is written in the code; this file maps it to Greek.
// t("Applications per month, {year}", { year }) translates and fills {placeholders};
// a text without a Greek entry stays in English. The choice is a per-browser preference (localStorage).
"use strict";

const i18n = (() => {
  const EL = {
    // ---- navigation, header, dialogs
    "Overview": "Επισκόπηση",
    "Assistant": "Βοηθός",
    "Branches": "Καταστήματα",
    "Data quality": "Ποιότητα δεδομένων",
    "Exposure graph": "Γράφος έκθεσης",
    "Status": "Κατάσταση",
    "Language": "Γλώσσα",
    "Connect": "Σύνδεση",
    "Key set": "Κλειδί ορίστηκε",
    "API key": "Κλειδί API",
    "Sign in with Microsoft": "Σύνδεση με Microsoft",
    "Sign out": "Αποσύνδεση",
    "Signed in as": "Συνδεδεμένος ως",
    "Connect to the API": "Σύνδεση στο API",
    "The data routes need an API key on this environment. It is sent with every request from this tab and is forgotten when you close it.":
      "Τα δεδομένα χρειάζονται κλειδί API σε αυτό το περιβάλλον. Στέλνεται με κάθε αίτημα από αυτή την καρτέλα και ξεχνιέται όταν την κλείσετε.",
    "Local: the value of API_KEYS in your .env. Dev: the Key Vault secret api-keys-dev.":
      "Τοπικά: η τιμή του API_KEYS στο .env σας. Dev: το μυστικό api-keys-dev στο Key Vault.",
    "Cancel": "Ακύρωση",
    "Data as of {date}": "Δεδομένα έως {date}",
    "Warehouse unavailable": "Η αποθήκη δεδομένων δεν είναι διαθέσιμη",

    // ---- sign-in and credentials
    "Sign in": "Σύνδεση",
    "Use your athtech Microsoft account. Team 2 members only.": "Χρησιμοποιήστε τον λογαριασμό Microsoft του athtech. Μόνο για μέλη της Ομάδας 2.",
    "This dashboard reads everything through the Loan Analytics API, which accepts only signed-in Team 2 members on this environment.":
      "Ο πίνακας διαβάζει τα πάντα μέσω του Loan Analytics API, που σε αυτό το περιβάλλον δέχεται μόνο συνδεδεμένα μέλη της Ομάδας 2.",
    "Enter an API key to load the data.": "Δώστε ένα κλειδί API για να φορτωθούν τα δεδομένα.",
    "This dashboard reads everything through the Loan Analytics API, and every data route needs a credential.":
      "Ο πίνακας διαβάζει τα πάντα μέσω του Loan Analytics API, και κάθε διαδρομή δεδομένων χρειάζεται διαπιστευτήριο.",
    "Enter API key": "Εισαγωγή κλειδιού API",
    "Your session has ended. Sign in again.": "Η συνεδρία σας έληξε. Συνδεθείτε ξανά.",
    "The API rejected the credential. Enter a valid one.": "Το API απέρριψε το διαπιστευτήριο. Δώστε ένα έγκυρο.",
    "Only Team 2 members can sign in.": "Μόνο μέλη της Ομάδας 2 μπορούν να συνδεθούν.",
    "Sign-in was cancelled.": "Η σύνδεση ακυρώθηκε.",
    "The sign-in window was blocked. Allow pop-ups for this site and try again.":
      "Το παράθυρο σύνδεσης μπλοκαρίστηκε. Επιτρέψτε τα αναδυόμενα παράθυρα για αυτή τη σελίδα και δοκιμάστε ξανά.",
    "Sign-in failed. Try again.": "Η σύνδεση απέτυχε. Δοκιμάστε ξανά.",

    // ---- errors
    "The API could not be reached.": "Δεν ήταν δυνατή η επικοινωνία με το API.",
    "The assistant is not available on this environment. ": "Ο βοηθός δεν είναι διαθέσιμος σε αυτό το περιβάλλον. ",
    "Azure OpenAI is not configured or is down; the rest of the dashboard works without it. ":
      "Το Azure OpenAI δεν έχει ρυθμιστεί ή δεν λειτουργεί· ο υπόλοιπος πίνακας λειτουργεί κανονικά. ",
    "Sign in again with the button in the top bar.": "Συνδεθείτε ξανά με το κουμπί στην επάνω μπάρα.",
    "Use the key button in the top bar to enter a valid API key.": "Πατήστε το κουμπί κλειδιού στην επάνω μπάρα για να δώσετε έγκυρο κλειδί API.",
    "The data warehouse is unavailable or still waking up. Try again in a minute.":
      "Η αποθήκη δεδομένων δεν είναι διαθέσιμη ή ακόμα ξεκινά. Δοκιμάστε ξανά σε ένα λεπτό.",
    "correlation id {id}": "αναγνωριστικό συσχέτισης {id}",
    "error:unauthorized": "Μη εξουσιοδοτημένο αίτημα",
    "error:not_found": "Δεν βρέθηκε",
    "error:method_not_allowed": "Η μέθοδος δεν επιτρέπεται",
    "error:validation_error": "Το αίτημα δεν είναι έγκυρο",
    "error:data_unavailable": "Η πηγή δεδομένων δεν είναι διαθέσιμη, δοκιμάστε αργότερα",
    "error:internal_error": "Κάτι πήγε στραβά",
    "error:network_error": "Δεν ήταν δυνατή η επικοινωνία με το API.",

    // ---- common
    "Loading…": "Φόρτωση…",
    "No data for this selection.": "Δεν υπάρχουν δεδομένα για αυτή την επιλογή.",
    "Apply": "Εφαρμογή",
    "Period": "Περίοδος",
    "Branch": "Κατάστημα",
    "Product": "Προϊόν",
    "Month": "Μήνας",
    "Year": "Έτος",
    "All branches": "Όλα τα καταστήματα",
    "Search": "Αναζήτηση",
    "Previous": "Προηγούμενη",
    "Next": "Επόμενη",
    "None": "Κανένα",
    "Yes": "Ναι",
    "No": "Όχι",
    "Unknown": "Άγνωστο",
    "{v} days": "{v} ημέρες",

    // ---- metrics (labels and definitions come from /metadata/metrics in English)
    "Applications": "Αιτήσεις",
    "Requested amount": "Αιτούμενο ποσό",
    "Approval rate": "Ποσοστό έγκρισης",
    "Average decision time": "Μέσος χρόνος απόφασης",
    "High DTI share": "Μερίδιο υψηλού DTI",
    "DTI band share": "Κατανομή ανά ζώνη DTI",
    "30-day delinquency rate": "Ποσοστό καθυστέρησης 30+ ημερών",
    "Outstanding balance": "Ανεξόφλητο υπόλοιπο",
    "Manual review rate": "Ποσοστό χειροκίνητου ελέγχου",
    "number of loan applications": "πλήθος αιτήσεων δανείου",
    "total amount requested in the applications": "συνολικό ποσό που ζητήθηκε στις αιτήσεις",
    "approved / (approved + rejected)": "εγκεκριμένες / (εγκεκριμένες + απορριφθείσες)",
    "days from submission to decision, averaged over decided applications":
      "ημέρες από την υποβολή ως την απόφαση, κατά μέσο όρο στις αιτήσεις με απόφαση",
    "applications with a debt-to-income ratio of 35% or more / applications with a DTI":
      "αιτήσεις με λόγο χρέους προς εισόδημα 35% ή περισσότερο / αιτήσεις με DTI",
    "share of applications in each debt-to-income band (whole portfolio only)":
      "μερίδιο αιτήσεων σε κάθε ζώνη χρέους προς εισόδημα (μόνο για όλο το χαρτοφυλάκιο)",
    "active loans 30 or more days past due / active loans": "ενεργά δάνεια με καθυστέρηση 30+ ημερών / ενεργά δάνεια",
    "outstanding principal of the loans": "ανεξόφλητο κεφάλαιο των δανείων",
    "applications sent to manual review / applications": "αιτήσεις που πήγαν για χειροκίνητο έλεγχο / αιτήσεις",
    "After data-quality checks": "Μετά τους ελέγχους ποιότητας",
    "Sum of requested principal": "Άθροισμα αιτούμενου κεφαλαίου",
    "Approved ÷ (approved + rejected)": "Εγκεκριμένες ÷ (εγκεκριμένες + απορριφθείσες)",
    "Application to decision": "Από την αίτηση ως την απόφαση",
    "Debt-to-income 35% or more": "Χρέος προς εισόδημα 35% ή περισσότερο",
    "Active loans 30+ days late": "Ενεργά δάνεια με καθυστέρηση 30+ ημερών",
    "Outstanding principal": "Ανεξόφλητο κεφάλαιο",
    "Sent to manual review": "Σε χειροκίνητο έλεγχο",

    // ---- products, statuses, entities, DQ dimensions
    "Personal loan": "Προσωπικό δάνειο",
    "Green home loan": "Πράσινο δάνειο κατοικίας",
    "New car loan": "Δάνειο καινούργιου αυτοκινήτου",
    "Fixed-rate mortgage": "Στεγαστικό σταθερού επιτοκίου",
    "SME working capital": "Κεφάλαιο κίνησης ΜμΕ",
    "Approved": "Εγκεκριμένη",
    "Rejected": "Απορριφθείσα",
    "Submitted": "Υποβληθείσα",
    "Under review": "Υπό εξέταση",
    "Withdrawn": "Αποσύρθηκε",
    "Loan applications": "Αιτήσεις δανείου",
    "Customers": "Πελάτες",
    "Repayments": "Αποπληρωμές",
    "Transactions": "Συναλλαγές",
    "completeness": "πληρότητα",
    "validity": "εγκυρότητα",
    "uniqueness": "μοναδικότητα",
    "consistency": "συνέπεια",
    "integrity": "ακεραιότητα",
    "timeliness": "επικαιρότητα",

    // ---- overview
    "Portfolio overview": "Επισκόπηση χαρτοφυλακίου",
    "The 8 governed KPIs from the Gold layer, with the same definitions as the Power BI report.":
      "Οι 8 ελεγχόμενοι δείκτες από το επίπεδο Gold, με τους ίδιους ορισμούς με το report του Power BI.",
    "Applications per year": "Αιτήσεις ανά έτος",
    "Applications per month, {year}": "Αιτήσεις ανά μήνα, {year}",
    "Debt-to-income bands": "Ζώνες χρέους προς εισόδημα",
    "By branch": "Ανά κατάστημα",
    "Open branch drill-through": "Ανάλυση ανά κατάστημα",
    "Under 20%": "Κάτω από 20%",
    "Over 50%": "Πάνω από 50%",
    "Share of applications in each debt-to-income band. Gold keeps this KPI for the whole portfolio only, so the period and branch filters do not apply.":
      "Μερίδιο αιτήσεων σε κάθε ζώνη χρέους προς εισόδημα. Το Gold κρατά αυτόν τον δείκτη μόνο για όλο το χαρτοφυλάκιο, οπότε τα φίλτρα περιόδου και καταστήματος δεν εφαρμόζονται.",
    "Avg decision (days)": "Μέση απόφαση (ημέρες)",
    "Delinquency 30+": "Καθυστέρηση 30+",
    "Outstanding": "Ανεξόφλητο",
    "{n} branch · from POST ": "{n} κατάστημα · από POST ",
    "{n} branches · from POST ": "{n} καταστήματα · από POST ",

    // ---- assistant
    "Portfolio assistant": "Βοηθός χαρτοφυλακίου",
    "Ask a question in plain language. Every number in an answer is copied from a tool result over the Gold layer, and the evidence is shown under it.":
      "Κάντε μια ερώτηση σε απλή γλώσσα. Κάθε αριθμός στην απάντηση προέρχεται από αποτέλεσμα εργαλείου πάνω στο επίπεδο Gold, και τα στοιχεία φαίνονται από κάτω.",
    "e.g. Which branches have the highest delinquency?": "π.χ. Ποια καταστήματα έχουν τη μεγαλύτερη καθυστέρηση;",
    "Ask": "Ρωτήστε",
    "Ask about the portfolio": "Ρωτήστε για το χαρτοφυλάκιο",
    "Sends POST ": "Στέλνει POST ",
    ". Questions about actions or raw SQL are refused before the model is called.":
      ". Ερωτήσεις για ενέργειες ή για SQL απορρίπτονται πριν κληθεί το μοντέλο.",
    "Try asking": "Δοκιμάστε να ρωτήσετε",
    "Tools it can use": "Εργαλεία που χρησιμοποιεί",
    "It will not": "Δεν θα",
    "Approve or change loans, run SQL, show personal data, or answer from memory without a tool result.":
      "Εγκρίνει ή αλλάζει δάνεια, εκτελεί SQL, δείχνει προσωπικά δεδομένα ή απαντά από μνήμης χωρίς αποτέλεσμα εργαλείου.",
    "What was the approval rate by branch in 2025?": "Ποιο ήταν το ποσοστό έγκρισης ανά κατάστημα το 2025;",
    "Which product has the highest outstanding balance?": "Ποιο προϊόν έχει το μεγαλύτερο ανεξόφλητο υπόλοιπο;",
    "Show the 30-day delinquency rate by month for 2025.": "Δείξε το ποσοστό καθυστέρησης 30+ ημερών ανά μήνα για το 2025.",
    "What is the connected exposure for application LA000225?": "Ποια είναι η συνδεδεμένη έκθεση για την αίτηση LA000225;",
    "One KPI for the whole portfolio or by branch, product, month or year, optionally for a date range":
      "Ένας δείκτης για όλο το χαρτοφυλάκιο ή ανά κατάστημα, προϊόν, μήνα ή έτος, προαιρετικά για ένα διάστημα ημερομηνιών",
    "Records flagged or rejected by the data-quality rules": "Εγγραφές που σημειώθηκαν ή απορρίφθηκαν από τους κανόνες ποιότητας",
    "The available KPIs, their definitions and how recent the data is": "Οι διαθέσιμοι δείκτες, οι ορισμοί τους και πόσο πρόσφατα είναι τα δεδομένα",
    "The household around one application and its total outstanding balance": "Το νοικοκυριό γύρω από μία αίτηση και το συνολικό ανεξόφλητο υπόλοιπό του",
    "Thinking…": "Σκέφτεται…",
    "Unavailable": "Μη διαθέσιμος",
    "Answered": "Απαντήθηκε",
    "Refused": "Απορρίφθηκε",
    "No data": "Χωρίς δεδομένα",
    "Incomplete": "Ελλιπής",
    "{n} tool call": "{n} κλήση εργαλείου",
    "{n} tool calls": "{n} κλήσεις εργαλείων",
    "data as of {date}": "δεδομένα έως {date}",
    "Outside what the assistant can do": "Εκτός των δυνατοτήτων του βοηθού",
    "{secs} · stopped before a full answer": "{secs} · σταμάτησε πριν από πλήρη απάντηση",
    "{n} tool round": "{n} γύρος εργαλείων",
    "{n} tool rounds": "{n} γύροι εργαλείων",
    "Filters applied": "Φίλτρα",
    "Source": "Πηγή",
    "No tool was run": "Δεν εκτελέστηκε εργαλείο",
    "Limitations": "Περιορισμοί",
    "no arguments": "χωρίς ορίσματα",
    "round {n}": "γύρος {n}",
    "✗ failed": "✗ απέτυχε",
    "Show trace ({n} step)": "Εμφάνιση ίχνους ({n} βήμα)",
    "Show trace ({n} steps)": "Εμφάνιση ίχνους ({n} βήματα)",
    "Hide trace ({n} step)": "Απόκρυψη ίχνους ({n} βήμα)",
    "Hide trace ({n} steps)": "Απόκρυψη ίχνους ({n} βήματα)",
    "Evidence · {title}": "Στοιχεία · {title}",
    "as of {date}": "έως {date}",
    "Group": "Ομάδα",
    "Value": "Τιμή",
    "KPI": "Δείκτης",
    "UNKNOWN (invalid code)": "UNKNOWN (μη έγκυρος κωδικός)",
    "Whole portfolio": "Όλο το χαρτοφυλάκιο",
    "{total} in total · first {shown} shown": "{total} συνολικά · εμφανίζονται οι πρώτες {shown}",
    "{total} in total": "{total} συνολικά",
    "Data-quality exceptions · {count}": "Εξαιρέσεις ποιότητας δεδομένων · {count}",
    "Rule": "Κανόνας",
    "Action": "Ενέργεια",
    "Description": "Περιγραφή",
    "{members} members · {outstanding} outstanding · {late} delinquent":
      "{members} μέλη · {outstanding} ανεξόφλητα · {late} σε καθυστέρηση",
    "Connected exposure · {summary}": "Συνδεδεμένη έκθεση · {summary}",
    "Application": "Αίτηση",
    "Customer": "Πελάτης",
    "30+ days late": "Καθυστέρηση 30+ ημερών",
    "Available KPIs": "Διαθέσιμοι δείκτες",
    "Unit": "Μονάδα",
    "Definition": "Ορισμός",
    "Field": "Πεδίο",

    // ---- branches
    "Application funnel": "Ροή αιτήσεων",
    "Applications by product": "Αιτήσεις ανά προϊόν",
    "Approval rate by product": "Ποσοστό έγκρισης ανά προϊόν",
    "Delinquency 30+ by product": "Καθυστέρηση 30+ ανά προϊόν",
    "Counting data-quality exceptions…": "Καταμέτρηση εξαιρέσεων ποιότητας…",
    "{applications} applications since 2016 · data as of {date}": "{applications} αιτήσεις από το 2016 · δεδομένα έως {date}",
    "{share} of portfolio": "{share} του χαρτοφυλακίου",
    "Portfolio {value}": "Χαρτοφυλάκιο {value}",
    "Decided": "Με απόφαση",
    "Active loans": "Ενεργά δάνεια",
    "Delinquent 30+": "Σε καθυστέρηση 30+",
    "Decided = approved + rejected. Active loans are approved loans not yet paid off.":
      "Με απόφαση = εγκεκριμένες + απορριφθείσες. Ενεργά δάνεια είναι τα εγκεκριμένα που δεν έχουν εξοφληθεί.",
    "{n} data-quality exceptions": "{n} εξαιρέσεις ποιότητας δεδομένων",
    " at this branch: {rejected} rejected, {flagged} flagged": " σε αυτό το κατάστημα: {rejected} απορρίφθηκαν, {flagged} σημειώθηκαν",
    "View in Data quality": "Προβολή στην Ποιότητα δεδομένων",

    // ---- data quality
    "Data-quality exceptions": "Εξαιρέσεις ποιότητας δεδομένων",
    "Records the pipeline rejected or flagged, with the rule that failed. Rejected records are kept out of the KPIs; customer records appear only by hashed key.":
      "Εγγραφές που το pipeline απέρριψε ή σημείωσε, με τον κανόνα που απέτυχε. Οι απορριφθείσες μένουν εκτός δεικτών· οι πελάτες εμφανίζονται μόνο με κρυπτογραφημένο κλειδί.",
    "Rule failures": "Αποτυχίες κανόνων",
    "One row per record and failed rule": "Μία γραμμή ανά εγγραφή και κανόνα που απέτυχε",
    "Quarantined, kept out of Gold": "Σε καραντίνα, εκτός Gold",
    "Flagged": "Σημειώθηκαν",
    "Kept in Gold with a warning": "Μένουν στο Gold με προειδοποίηση",
    "Rejected share": "Μερίδιο απορρίψεων",
    "Rejected ÷ all rule failures": "Απορριφθείσες ÷ όλες οι αποτυχίες",
    "All": "Όλες",
    "Reject": "Απόρριψη",
    "Flag": "Σημείωση",
    "All rules": "Όλοι οι κανόνες",
    "e.g. batch_001": "π.χ. batch_001",
    "Batch": "Παρτίδα",
    "Record": "Εγγραφή",
    "Entity": "Οντότητα",
    "Reason": "Αιτία",
    "Dimension": "Διάσταση",
    "Detected (UTC)": "Εντοπίστηκε (UTC)",
    "No exceptions match these filters.": "Καμία εξαίρεση δεν ταιριάζει με αυτά τα φίλτρα.",
    "Showing {from}–{to} of {total} · from GET ": "Εμφανίζονται {from}–{to} από {total} · από GET ",
    "From GET ": "Από GET ",

    // ---- exposure
    "Connected exposure": "Συνδεδεμένη έκθεση",
    "Follows the knowledge graph from one application to the applicant's household and every loan connected to it. Customers appear only by node key.":
      "Ακολουθεί τον γράφο γνώσης από μία αίτηση στο νοικοκυριό του αιτούντα και σε κάθε συνδεδεμένο δάνειο. Οι πελάτες εμφανίζονται μόνο με κλειδί κόμβου.",
    "LA followed by 6 digits": "LA ακολουθούμενο από 6 ψηφία",
    "Application ID": "Κωδικός αίτησης",
    "Find exposure": "Εύρεση έκθεσης",
    "Applicant": "Αιτών",
    "Same household": "Ίδιο νοικοκυριό",
    "{n} application": "{n} αίτηση",
    "{n} applications": "{n} αιτήσεις",
    "Household outstanding": "Ανεξόφλητο νοικοκυριού",
    "Across all connected applications": "Σε όλες τις συνδεδεμένες αιτήσεις",
    "Connected customers": "Συνδεδεμένοι πελάτες",
    "Including the applicant": "Μαζί με τον αιτούντα",
    "Connected applications": "Συνδεδεμένες αιτήσεις",
    "Of every household member": "Όλων των μελών του νοικοκυριού",
    "Graph path": "Διαδρομή στον γράφο",
    "Application {id}": "Αίτηση {id}",
    "Customer {id}": "Πελάτης {id}",
    "Household": "Νοικοκυριό",
    "{n} more customer": "{n} ακόμη πελάτης",
    "{n} more customers": "{n} ακόμη πελάτες",
    "{n} more application": "{n} ακόμη αίτηση",
    "{n} more applications": "{n} ακόμη αιτήσεις",
    "Node": "Κόμβος",
    "Details": "Λεπτομέρειες",
    "Start": "Αφετηρία",
    "30+ days past due": "Καθυστέρηση 30+ ημερών",
    "Current": "Ενήμερο",

    // ---- status
    "Service": "Υπηρεσία",
    "Data": "Δεδομένα",
    "Your connection": "Η σύνδεσή σας",
    "Credential": "Διαπιστευτήριο",
    "Microsoft sign-in ({user})": "Σύνδεση Microsoft ({user})",
    "Not signed in": "Δεν έχετε συνδεθεί",
    "Kept": "Αποθήκευση",
    "In this browser tab only (sessionStorage)": "Μόνο σε αυτή την καρτέλα (sessionStorage)",
    "API reference": "Τεκμηρίωση API",
    "Swagger UI at /docs": "Swagger UI στο /docs",
    "Change API key": "Αλλαγή κλειδιού API",
    "Is the API up, can it reach the Gold layer, and how fresh is the data.":
      "Λειτουργεί το API, φτάνει στο επίπεδο Gold, και πόσο πρόσφατα είναι τα δεδομένα.",
    "Environment": "Περιβάλλον",
    "Version": "Έκδοση",
    "Sign in to check the data connection.": "Συνδεθείτε για να ελεγχθεί η σύνδεση με τα δεδομένα.",
    "Enter an API key to check the data connection.": "Δώστε κλειδί API για να ελεγχθεί η σύνδεση με τα δεδομένα.",
    "Warehouse": "Αποθήκη δεδομένων",
    "Reachable": "Διαθέσιμη",
    "Data as of": "Δεδομένα έως",
    "Refreshed": "Ανανεώθηκε",
  };

  const read = () => { try { return localStorage.getItem("lang") === "el" ? "el" : "en"; } catch { return "en"; } };
  let lang = read();
  document.documentElement.lang = lang;

  function t(text, vars) {
    let s = lang === "el" && Object.hasOwn(EL, text) ? EL[text] : text;
    if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
    return s;
  }

  return {
    t,
    // pick the singular or plural English text, then translate it; {n} is filled with the count
    tn: (n, one, other, vars = {}) => t(n === 1 ? one : other, { n, ...vars }),
    has: (text) => lang === "el" && Object.hasOwn(EL, text),
    get lang() { return lang; },
    locale: () => (lang === "el" ? "el-GR" : "en-GB"),
    set(next) {
      lang = next === "el" ? "el" : "en";
      try { localStorage.setItem("lang", lang); } catch { /* storage blocked: this page only */ }
      document.documentElement.lang = lang;
    },
    // Static text in index.html: data-i18n holds the English text, data-i18n-placeholder / -title likewise.
    applyStatic() {
      for (const n of document.querySelectorAll("[data-i18n]")) n.textContent = t(n.dataset.i18n);
      for (const n of document.querySelectorAll("[data-i18n-placeholder]")) n.placeholder = t(n.dataset.i18nPlaceholder);
      for (const n of document.querySelectorAll("[data-i18n-title]")) n.title = t(n.dataset.i18nTitle);
    },
  };
})();

const { t, tn } = i18n;
