import { Injectable } from "@angular/core";
import { Subject } from "rxjs";

@Injectable({ providedIn: 'root'})
export class MessageService{
    private subject = new Subject<Message>();

    sendMessage(message: Message) {
        this.subject.next(message);
    }

    getMessage() {
        return this.subject.asObservable();
    }
}

export class MessageQueues {
    public static CAR_PICKER_QUEUE = 'carPicker'
    public static PART_SEARCH_QUEUE = 'partSearch'
}

export class Message {
    private queue: string;
    private payload: object;

    constructor(queue: string, payload: object) {
        this.queue = queue;
        this.payload = payload;
    }

    getQueue() {
        return this.queue;
    }

    getPayload() {
        return this.payload;
    }

    setQueue(queue: string) {
        this.queue = queue;
    }

    setPayload(payload: object) {
        this.payload = payload;
    }
}