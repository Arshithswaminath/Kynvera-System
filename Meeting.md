Summary

### Action Items

- [ ]  Obtain the proper email domain/address for Ajman Municipality to enable email-to-ticket automation
- [ ]  Arrange payment for the email integration service (not free)
- [ ]  Redesign the service ticket UI with a light orange-based color scheme (white + orange preferred) for Ajman Municipality
- [ ]  Add per-field Arabic translation with a translate icon
- [ ]  Remove "chargeable" field; update "reported by" to use pre-designated department representatives only
- [ ]  Replace hardcoded 10% overhead with a configurable per-company markup field (options: 0, 5, 10, 15, 20, 25%)
- [ ]  Enable cost module only after ticket reaches "work started" status
- [ ]  Implement two-stage ticket closing: service provider closes first, then client operations verifies and closes
- [ ]  Add invoice flow: after operations approval, invoice sent to both finance and operations teams
- [ ]  Fix date/timezone display issue in service report
- [ ]  Prepare demo with Ajman Municipality tomorrow

---

### Contract & Admin Context

- Current LPO is in place; a new contract starts from July
- A P.O. was received for a 3-month extension; invoicing is pending
- An increase in new job applications is being received (multiple per day)

---

### Ajman Municipality Service Ticket System — Overview

- The system is being adapted/redesigned from the existing Injaz service ticket platform
- Goal: automate the service ticket flow for Ajman Municipality
- The application will be owned and operated by the service management company, with Injaz and other vendors as assignees

---

### Email-to-Ticket Automation

- Inbound emails should automatically create a draft ticket in the system — this functionality is already built and online
- Email must route to a notification/inbox page rather than a generic address
- Email integration requires a paid setup; a proper domain email for Ajman Municipality is needed before going live
- A dashboard indicator will show when a draft ticket has been created from an inbound email

---

### Ticket Form Design

- Fields will include: location (auto-filled if from email), complaint specification (free text or pre-filled options e.g. "HVAC system problems"), and reported-by
- **Reported by:** Only pre-designated department representatives per building/department will fill the form — not all employees
- **Arabic translation:** A translate icon will be added per individual field (not page-wide) to toggle between Arabic and English
- "Chargeable" field to be removed

---

### Ticket Workflow & Access Model

- **Ticket creation:** Municipality point of contact raises a ticket (status: Open)
- **Assignment:** Municipality admin assigns the ticket to a vendor team (e.g. Injaz, NAFCO, etc.) from their pool of service providers
- **Vendor work:** Technician attends site → logs updates → marks work started → completes work and enters notes
- **Cost entry:** Vendor (technician or supervisor) fills in manpower and material costs — cost module only unlocked after "work started"
- **Verification (Stage 1 — Service Provider):** Supervisor verifies work, adds markup/overhead, adds signature, and closes from their side
- **Verification (Stage 2 — Client Operations):** Municipality operations team reviews all details, verifies, and closes from their end
- **Finance:** After operations approval, invoice is generated and sent to both the finance team and operations for reference
- **Municipality access:** Can view all ticket details and add comments in logs, but **cannot edit status**

---

### Cost & Markup Configuration

- The previously hardcoded 10% overhead will be removed
- Markup will be a manual, per-company configurable field with preset options (0%, 5%, 10%, 15%, 20%, 25%)
- Cost summary and invoice details are only surfaced after work completion

---

### Service Report & Invoice

- Service report includes: closed date, work description, overhead/markup, activity log, and supervisor signature
- A date/timezone bug was identified in the report and needs to be fixed
- Invoice will reference the service ticket and be distributed to both finance and operations
- Free tier limited to 3 companies/vendors; additional vendors require a paid upgrade

---

### UI / Branding

- Current dark theme is considered too dark; a lighter design is preferred
- Three color options discussed: white + orange, navy blue + orange, black + orange — orange is the consistent brand element
- Decision: go with a light (white + orange) theme

---

### Timeline

- Demo with Ajman Municipality targeted for **tomorrow**

Notes

Transcript

Yesterday I went to theOkay, two more. Sorry?

Yesterday I went to the doctor.

Okay. Is it like you have a problem or?

No, I have a deep checkup. What is this?

This is We can generate a report from the repository where the model is. Just all the MCs? The rectifications are just waiting for our audience to send us service reports. This place here? Yes. Yes. This is the new contract value. Till this month we have this LPO and the contract is starting from next month. From July the contract is starting. Ah, we all decided the invoice for the P.O. that they sent us? Yes sir, they gave us a P.O. for three months for the extension. Okay. It's all waiting for this. -

All right. So we have to look for-Did you notice that we have more application right now is process, right?

For the new stuff?

Yes, more. At least per day we are getting more. Sir? Today... Three applications went for them.

That's why I did it. That's why.

These guys, these guys, so today you got FM guy. If I, if she was handling, she would tell that we are not hiring anyone now.

Yeah, yeah, yeah.

For mention they would say nobody but now the guy came on morning he got approval now Staff is like that, yeah. Okay, so to start with now we are looking for Ajman Missibility. So far the things that they asked for is to automate their service ticket flow. So maybe we can, we have to redesign this thing, the service ticket that we created for Injaz. We can redesign our UI color wise everything and functional wise I need your opinion how we need to maintain or give the service to them.

So they ask for that email has to come from outside it should automatically creates a draft ticket which is already done. Done? Yeah it is done it is online now I mean which means it is on there so I just need to get any one of the email address which means that reception address or something like that if I got the proper domain that we are going to use for Rajman Municipality We have that email, right?

We have or we can create an Ajman in this particular email address itself. We will ask the faculty for that. No, no.

No, no, no, it won't be anymore. Email has to go to the notification page.

Oh, okay. Makes sense.

At the rate, we can wear a top.

Yeah, we have that option.

Yeah.

Yeah, then we can go with that. So once it's connected, then we can Have the possibility to have the draft ticket here and once somebody goes there, they can just change the ticket. but the floor wise Do we want to change anything or?

No, I guess I want to see how it will go. Now, send an email.

No, no. Email-wise, it's not config because I didn't add that email here. Code wise I build it, but practical wise I need that email, I need some payment to be done for that it's not free to push an email to get an email it's charged yeah so once it's done we will let's say we receive an email here so I will be putting a dashboard here saying that draft email or draft ticket came from the emailing Okay, and then once you go into that, so this is how it will be.

Let me zoom in a little. Location, these details will be auto filled. If that is coming from the email, if not, it will be clicked. Click here.

So the client has to, this will come by default?

Yes sir. And find location, we list all the locations. All the, whatever they have they will get. So now, I just add only Injaz, head office. So once we have everything, we'll go with everything. Okay. properties wise let's say for like ground floor or something like that or we can just use this drop down to have these options So I feel that these things will be automated once we have that email.

Yes, okay.

Reception areas and everything, this will be location, complaint specification, either they can write the complaint, on their own or they can use the pre-filled complaints, HVAC system problems, something like that.

Does it have Yes, that's a better one.

Maybe we will have a field there as an Arabic and we will have a small icon for translate. If they click translate automatically goes to English automatically comes back to Arabic. Do you want to do for whole page or do you want to do for a particular field? Location field, each fields. you Not for everything. Not for everything. Each field. Let's say for fine projects, if you're typing-Everything that will be later on.

I do share that with all of you.

It will be. It's more. But Google itself has its own Arabic translator. Once I go here, if I go for translate, I can choose it to English or something. If I go here, another language.

Why is it so blurry?

Because I am just a machine.

No, no, even for me it's too blur. Yeah, because I adjusted.

You should adjust. You adjusted. No, no, I didn't.

Yeah, you see?

Okay. Yeah, the next one. Yeah.

See. Oh! Yeah, that's great.

Is it relevant? Is it straightforward?

I'll come in next time.

Can you repeat this part? We will be adding those guys name and then it goes like this. We will remove this chargeable.

Let's say it be reported by. They will select from each...

Department or each building would need somebody to be there.

Yeah.

So mostly if Yes.

to write his name that I'm recording this one. The guy that is already pre-designed, selected by their department, he is the first contact point reporting all the complaints. That one would be better for them.

If I am an employee, then I can say that I have this one in mind. So that guy is the one that is filling that list. Not everyone. So they have two options.

will be here. Once they confirm, they can just go with the create ticket. That's it. And it's created. It is open now.

Value 800 car guru, look at that.

Once it is created it will be like this. It will open. Now ticket open it goes to our team now. Our supervisor team and the team members will be listed here. Or else we will be having an option and then they have to go with their technicians. So once there and we have the update status in the side of it. On hold reasons and cost summary do we need to do? Keep it or do you have to remove it?

No, not here. I'll tell you what. In here, because this will be their application.

Yes. Right. But we will be the one who will be assigning and doing the things, right?

No, no, no, I do understand. This will be their application.

They will be using it.

They can use it with Inja's and they can use it for others. Yes. So it means that the team here will be assigned to which company? I'm the one holding the application. Yeah. I'm the owner. Yes.

I'm the biggest party. Yes.

So I have not only in jazz, in jazz one of my services provided. There are many. So here assigned to, assigned technician or assigned to the team, my team. That one goes with the assigned. If I select in jazz, then all in jazz will come there. Maybe you will have NAFCO. maybe I have a my NCC TV anything anything got it so from mine as Assistant administrator from the municipality, the technical team, I will assign it to whomever I want.

So that one is not going to be limited to Injaz. It's going to be listed to all the vendors that they provide the service for.

They provide the service for and if they, so it's all up to them, if they want to add those team here, they can add it. If they don't want, it's up to them.

No, if they want to add, they need to contact.

Contact us, yes. Contact us. Build all these. Everything. Push it up. Yeah. Yeah. It is what it is, yeah.

Three users only for free. Three companies will have listed. Three companies. The companies will have their star, their religion, uploaded yes that data so any if this is welcome Free with free only. If you want more to be uploaded, that would be, let's say, Let's say, yeah.

Yeah, you understand. I got it now. So now my team will be like their company team is.

Yes. Then these are the team that they can go for.

Yes, so after they select Injaas, our supervisor will be seeing this application. Our supervisor will be the one who assigns this decade to his teammates, which is his technicians. Then it goes and each and every locks will be updated to them via email and also they can see it in the which means in jazz's point of contact person will see it admin will see it and he will assign to his supervisor and then it goes to the technician Where it goes, how it goes, how long it takes, everything.

Okay. Okay. So, locks has to be like Filled with all the details and details will be like this is okay summary and for cost do we need to add this manpower cost and material subtotal in the ticket or? What do they prefer?

From there and And they will see that also, but they will see it after it's been assigned. Yes. They will send everything. Then the contractor will fill these details.

Let's say if the contractor in jazz will be filling this manpower, how much people are required and what are the materials being utilized. They will fill and these details will be sent back. Once they click save, it goes there.

Go to them. Yeah. They will verify. Approve or reject. That's it.

It will have approve. Richard? The smell is hard Uh-huh.

Okay. Reassign in which means in the functional.

Maybe I will not give it to each other, give it to another. I think this one I will give it to another component. That kind of thing. I get it. You put yourself in their shoes.

Got it. So then these things should be for the vendor, not for the Ajmay municipality's perspective. Yes, yes. Got it. We can see the cost.

F, the assigning on activity details photos The cost will be based on the feedback from the service provider.

Photos they are supposed to add if they have any.

It will go to the service provider.

Yes. Okay. Done. And for the update status for this assign everything, do we need to give the access to them or to the service provider?

No, this is to the status provider.

Purely, right?

Yeah, yeah.

So only open status will be for them. After that, once it is moved to any vendor...

They can view all.

They can only read it? Yeah. Cannot edit it?

Yeah, but the status they cannot view.

Okay.

But they cannot change the status from their end.

From their end, okay. And we can let them to add any comments if they want in the logs, right? Yeah, yeah, yeah. Okay, that is done. And this thing... So the cost summary, everything has to be showed after the work completed, something like that? Yes. Thank you.

I will show you the floor chart.

Okay, so assign is done, assign and start if they do it and ticket is assigned and then they have to confirm so the site attended or not so And so here this will be the log for that. This will be distributed to their emails. And then once it is confirmed, it goes to the site attempted. Same as like that. And then Work started, maybe we can redesign these things. No, it's good. Okay, and then once the work is about to complete, they have to enter the notes, what is completed, what has been done.

I believe this is the area that the vendor has to... Comment the fields and also he needs to go to the cost. Cost, yes. Yes. So we need to enable that cost module only after the work started thing. Yes. Okay, got it. Let's test Mark it as completed and then now it's completed from the technician side now it went back to the supervisor supervisor supposed to check everything to verify so I'm calling it as verification stage so here he will start verifying so either supervisor can add the material and manpower cost or the technician but I feel suppose like supervisor will be adding these things all these things yes so once you start doing everything start verification will be there and he will just verify and here we added something like 10% it's overhead and this market price and everything do we need that okay Once it is done, this will be the logs.

So, we do not have to put that in the log divide. That 10% has been added, blah blah blah. That internal things andBut this 10 percentage will be varied among those service providers. I put this in Injaz's mind. So maybe other company won't need this 10% they may need something else right? So we need to put it like a manual way? Yes. So based on companies you can have the percentage? Any overhead just price if you want you can...

That's it.

Total will come. Total will come okay that's it so we are going to remove this overhead price. you If the field is mandated, no. So here I so that 10 percentage is Code advice is manual, I mean automated. Here they have to put markup price. Maybe I will remove that and will make them to use this. Based on the companies you can add whatever the markup you want to put. Yes. Total will be here and let's say they are going for 10, it will be added 10 and then.

Option 10, 15, 20, 25, stay.

Can you say that again?

Zero, ten, fifteen, yeah yeah. Really good. 10, 0, 10, 15, 20, 25, say it.

555, got it. Yeah, 5. 555, yeah.

And then the supervisor name and here goes the supervisor signature from the service provider and they will mention everything, they will disclose the ticket. I think it's mandatory. Let me sign. Okay. Ticket closed selling price. This is now the ticket has been closed. For Inja's perspective, what I did is, this goes to finance now. Sequentially to it, g m. So GM and the finance team will know that there's a service ticket created and we will get the invoice as well here, service report here.

So based on these, Our guys finance will be creating their invoice or those guys department work will start. So here I think we have to break that loop. Because we don't have to send, municipality don't have to send this to the finance or how that they will expect.

It should be from their finance, yes of course. So... So the service report after verification, then after that create invoice and invoice will send to the firm.

So we can stick with this loop. Like after closing it goes to your superior manager, whoever you want to assign and then it goes to finance for their review. Yes.

Finance to review and pay because they will have all the supporting documents in the service report.

Yes, service report and invoice. Maybe we need to check the service reports. Oh, that's nice. This is how it will be and service charges and things. This is for the invoice perspective and for the service report. I just want to see whether it's pumping up the locks. Okay, closed date, okay, we just closed, okay, dates are not correct I think, it's 11:35, it's supposed to be 3:35 something, I'll check that, work description is there, overhead price, activity log is there, so I believe it's a full thing and signature wise, this is supervisor signature from the service provider, who else need to sign this sir?

This? Yes. The patient accepted Municipality operation has to have their level of verification. First verification from the service provider side, second verification goes to their operation side, then it goes to finance. So who will be closing it fully? One part of closing will be done from the service provider.

So the service provider will be taking. They put their charges and everything, from my reporting documents, then from their end they complete it.

That will go to the operation, client operation.

I'm not going to go to the municipal, but I'll go to the client operation. They will verify everything, then they close it from their end. Once they close it from their end and it has an approval, Whatever they decided, the guy in the operation or their manager.

Manager. Whomever there, then from there it will go creating the invoice. Invoice finance, there they will run it.

Got it. So, okay. I just need to add one field for this time.

Invoice finance, then the invoice will go to them. To the finance? Okay, as well as the operation would have the invoice.

Invoice to refer that. Yes. Then I just need to like tweak something else.

That is it. And now the invoice to finance and the invoice to the operation. So, the Because they create the service provider created this process. So they need to have a reference on their invoice.

That invoice will come fromThere you go.

There you go. Yeah. Got it.

Okay, as like a color perspective, do you feel it's like, I mean color wise I will change it, something else. Yeah, yeah, yeah. It's too dark, I don't want this dark thing or do I, I mean either we have to have something something our own color brand or else we have to furnish for their color brand. What do you prefer?

Light gray? Mind. It was black and grey, black and orange, right?

It was like white and orange. We can have three combinations. White and orange, navy blue and orange, black and orange. Mostly the orange is the...

Yeah, yeah, yeah.

We'll go with that, right?

Very light. Good music does go very light. Got it.

Where is he at? -Okay.

Do we have another meeting?

Yes. Maybe yes.

Scenario as of now I have it in the mind. Once you give it I will cross check that. When do you prefer to close this and have a demo with them? Or we can... Tomorrow.

Got it. Sure. -