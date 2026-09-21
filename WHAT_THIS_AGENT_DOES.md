# When an AI assistant does something unexpected

An AI assistant can do more than answer questions. It can read documents, use an email account and take actions on someone's behalf. When something goes wrong, that creates a difficult question: how do we work out what happened and who was responsible?

The **Trusted Forensic Agent** helps people examine the available records of an AI assistant's activity. It connects the original request, the information the assistant received, the tools it used and the results of its actions. It produces a report showing what the records support and what is still unknown.

Imagine asking an assistant to summarise your inbox. An email contains an instruction telling it to send a confidential document to an outside address. The assistant follows that instruction and sends the document using your account.

A record saying that your account sent the email does not, by itself, show that you wanted it sent. The tool helps examine the difference between what you requested, what the assistant encountered and what actually happened.

In the demonstration, it connects those events and checks whether the email was within the assistant's permitted use. Being allowed to send email does not mean being allowed to send any document to any recipient. It also highlights missing records. If there is no reliable record of approval, the report says that approval cannot be established.

When several companies' services are involved, part of the story may be missing. The tool can show a known gap in the records, name the organisation holding the missing records and explain what information is needed. It does not fill the gap with a guess.

Several groups can use this working example:

- **Security teams and investigators** can practise examining an AI incident and identifying which records to preserve or request.
- **People building AI systems** can check whether they record enough information to explain their assistants' actions later.
- **Managers and people responsible for oversight** can use the demonstration and reports to understand where human approval, permissions and record keeping matter.
- **Researchers, teachers and students** can explore the method, inspect the code and test it with different examples.

The tool also packages the records, its analysis and its report together with a digital seal. Checking the original seal can reveal later changes. Another person can repeat the analysis and check whether it produces the same results. This makes the investigation easier to examine and challenge.

The current version is a research demonstration. It runs on prepared examples or records supplied in its required format; it does not collect information from live services. The demonstration uses a shared key included with the code, so anyone can replace both the package and its seal. A real deployment needs an independent party to hold and confirm the seal.

The tool cannot recover records that were never kept, prove someone's intentions or decide whether evidence will be accepted in court. It gives the people making those decisions a clearer account of the recorded actions, the supporting information and the questions that remain open.
