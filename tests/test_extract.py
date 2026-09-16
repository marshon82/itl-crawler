import unittest

from itl.contacts import discover_contact_urls, extract_lead, extract_emails, extract_phones
from itl.export import llm_pack


HTML = """
<html><head><title>Hughes Drywall | Chicago</title>
<script type="application/ld+json">
{"@type":"LocalBusiness","name":"Hughes Drywall",
 "telephone":"+1-708-555-0199","email":"mike.hughes@hughesdrywall.com",
 "address":{"@type":"PostalAddress","streetAddress":"10 Main St",
 "addressLocality":"Hickory Hills","addressRegion":"IL","postalCode":"60457"}}
</script></head>
<body>
<a href="/contact-us">Contact</a>
<a href="tel:+17085550199">Call</a>
<a href="mailto:mike.hughes@hughesdrywall.com">Email Mike</a>
<p>Chicago drywall and remodeling. Call (708) 555-0199.</p>
</body></html>
"""


class ExtractTests(unittest.TestCase):
    def test_phones(self):
        hits = extract_phones("Call (708) 555-0199 today", extra=["+1-708-555-0199"], source="tel")
        self.assertTrue(hits)
        self.assertEqual(hits[0].value, "(708) 555-0199")

    def test_generic_email_downranked(self):
        hits = extract_emails("info@shop.com and Jane.Lee@shop.com")
        values = [h.value for h in hits]
        self.assertIn("jane.lee@shop.com", values)
        named = next(h for h in hits if h.value.startswith("jane"))
        generic = next(h for h in hits if h.value.startswith("info"))
        self.assertGreater(named.confidence, generic.confidence)

    def test_lead_jsonld(self):
        lead = extract_lead(HTML, "https://hughesdrywall.com/")
        self.assertEqual(lead.company, "Hughes Drywall")
        self.assertTrue(lead.phones)
        self.assertTrue(lead.emails)
        self.assertIn("Hickory Hills", lead.address)
        self.assertGreater(lead.score, 0.5)

    def test_contact_links(self):
        urls = discover_contact_urls(HTML, "https://hughesdrywall.com/")
        self.assertTrue(any(u.endswith("/contact-us") for u in urls))

    def test_llm_pack(self):
        lead = extract_lead(HTML, "https://hughesdrywall.com/")
        pack = llm_pack([lead], profile="drywall contractor chicago")
        self.assertEqual(pack["messages"][0]["role"], "system")
        self.assertIn("leads", pack)
        self.assertEqual(pack["lead_count"], 1)


if __name__ == "__main__":
    unittest.main()
