import { Component, OnInit } from '@angular/core';
import {TreeService} from '../services/tree.service'
import { Message, MessageService, MessageQueues } from 'src/services/message.service';
import { delay, elementAt, filter, timeInterval } from 'rxjs';

declare var $: any;

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss']
})
export class AppComponent implements OnInit {
  
  title = 'parts-interchange-ui';
  carSelected = false;
  carId = 0;

  step = 0;

  constructor(private messageService: MessageService) {
    this.messageService.getMessage().pipe(filter((event) => event.getQueue() == MessageQueues.CAR_PICKER_QUEUE)).subscribe((msg: any) => {
      if (msg.getPayload()) {
        this.carId = msg.getPayload()['id']
        this.carSelected = true;
      } else {
        this.carSelected = false;
      }
    });
    this.messageService.getMessage().pipe(filter((event) => event.getQueue() == MessageQueues.CAR_PICKER_QUEUE)).subscribe((msg: any) => {
      this.step = 0;
    });

    this.messageService.getMessage().pipe(filter((event) => event.getQueue() == MessageQueues.PART_SEARCH_QUEUE)).subscribe((msg: any) => {
      this.step = 1;
    })
  }

  ngOnInit(): void {
    // $('.collapse').collapse()
  }

  collapseClicked(event: any) {
    console.log(event);
    let toggle_name = event.target.getAttribute('data-target');
    console.log(toggle_name);
    $(toggle_name).collapse()
  }


  setStep(step: number) {
    document
    this.step = step;
  }
  nextStep() {
    this.step += 1;
  }
  prevStep() {
    this.step -= 1;
  }
}